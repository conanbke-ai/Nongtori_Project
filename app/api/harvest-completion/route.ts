import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { isLocalRequest } from '@/app/api/_lib/farm-access';

export const runtime = 'edge';

type GradeInput = {
  gradeCode?: unknown;
  fruitCount?: unknown;
  totalWeightG?: unknown;
  averageConfidence?: unknown;
};

type HarvestCompletionInput = {
  runId?: unknown;
  farmId?: unknown;
  itemId?: unknown;
  cameraId?: unknown;
  startedAt?: unknown;
  completedAt?: unknown;
  grades?: unknown;
};

function cleanId(value: unknown) {
  return typeof value === 'string' && /^[A-Za-z0-9:_-]{1,120}$/.test(value) ? value : '';
}

function isoDate(value: unknown) {
  if (typeof value !== 'string') return '';
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : '';
}

export async function POST(request: Request) {
  await ensureSchema();
  const bindings = env as typeof env & { ROBOT_INGEST_TOKEN?: string };
  if (!isLocalRequest(request)) {
    if (!bindings.ROBOT_INGEST_TOKEN) {
      return NextResponse.json({ error: '로봇 연동 보안키가 아직 설정되지 않았습니다.' }, { status: 503 });
    }
    if (request.headers.get('authorization') !== `Bearer ${bindings.ROBOT_INGEST_TOKEN}`) {
      return NextResponse.json({ error: '로봇 인증에 실패했습니다.' }, { status: 401 });
    }
  }

  let body: HarvestCompletionInput;
  try {
    body = await request.json() as HarvestCompletionInput;
  } catch {
    return NextResponse.json({ error: 'JSON 요청 형식이 올바르지 않습니다.' }, { status: 400 });
  }

  const runId = cleanId(body.runId);
  const farmId = cleanId(body.farmId);
  const itemId = cleanId(body.itemId);
  const cameraId = body.cameraId == null || body.cameraId === '' ? null : cleanId(body.cameraId);
  const startedAt = isoDate(body.startedAt);
  const completedAt = isoDate(body.completedAt);
  const rawGrades = Array.isArray(body.grades) ? body.grades as GradeInput[] : [];
  const grades = rawGrades.map((grade) => ({
    gradeCode: typeof grade.gradeCode === 'string' ? grade.gradeCode.trim().toUpperCase() : '',
    fruitCount: Number(grade.fruitCount),
    totalWeightG: Number(grade.totalWeightG),
    averageConfidence: grade.averageConfidence == null ? null : Number(grade.averageConfidence),
  }));

  const invalidGrade = grades.some((grade) => !/^[A-Z0-9_-]{1,30}$/.test(grade.gradeCode)
    || !Number.isInteger(grade.fruitCount) || grade.fruitCount < 0
    || !Number.isFinite(grade.totalWeightG) || grade.totalWeightG < 0
    || (grade.averageConfidence !== null && (!Number.isFinite(grade.averageConfidence) || grade.averageConfidence < 0 || grade.averageConfidence > 1)));
  if (!runId || !farmId || !itemId || !startedAt || !completedAt || grades.length === 0 || invalidGrade || (body.cameraId && !cameraId)) {
    return NextResponse.json({ error: '수확 완료 데이터의 필수값 또는 등급 집계가 올바르지 않습니다.' }, { status: 400 });
  }
  if (Date.parse(completedAt) < Date.parse(startedAt)) {
    return NextResponse.json({ error: '완료 시각은 시작 시각보다 빠를 수 없습니다.' }, { status: 400 });
  }

  const relation = await env.DB.prepare(`SELECT fi.id AS item_id, c.id AS camera_id
      FROM farm_items fi LEFT JOIN cameras c ON c.id = ? AND c.farm_id = fi.farm_id AND c.status != 'ARCHIVED'
      WHERE fi.id = ? AND fi.farm_id = ? AND fi.status = 'ACTIVE'`)
    .bind(cameraId, itemId, farmId).first<{ item_id: string; camera_id: string | null }>();
  if (!relation || (cameraId && relation.camera_id !== cameraId)) {
    return NextResponse.json({ error: '농장·품목·로봇 연결 정보가 일치하지 않습니다.' }, { status: 404 });
  }

  const harvestedCount = grades.reduce((sum, grade) => sum + grade.fruitCount, 0);
  const totalWeightG = grades.reduce((sum, grade) => sum + grade.totalWeightG, 0);
  const now = new Date().toISOString();
  const jobId = crypto.randomUUID();
  const statements: D1PreparedStatement[] = [
    env.DB.prepare(`INSERT INTO harvest_runs(
        id, farm_id, item_id, camera_id, status, started_at, completed_at,
        harvested_count, total_weight_g, created_at, updated_at
      ) VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        farm_id = excluded.farm_id, item_id = excluded.item_id, camera_id = excluded.camera_id,
        status = 'COMPLETED', started_at = excluded.started_at, completed_at = excluded.completed_at,
        harvested_count = excluded.harvested_count, total_weight_g = excluded.total_weight_g,
        updated_at = excluded.updated_at`)
      .bind(runId, farmId, itemId, cameraId, startedAt, completedAt, harvestedCount, totalWeightG, now, now),
  ];
  for (const grade of grades) {
    statements.push(env.DB.prepare(`INSERT INTO harvest_grade_summaries(
        id, harvest_run_id, grade_code, fruit_count, total_weight_g, average_confidence, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(harvest_run_id, grade_code) DO UPDATE SET
        fruit_count = excluded.fruit_count, total_weight_g = excluded.total_weight_g,
        average_confidence = excluded.average_confidence`)
      .bind(crypto.randomUUID(), runId, grade.gradeCode, grade.fruitCount, grade.totalWeightG, grade.averageConfidence, now));
  }
  statements.push(env.DB.prepare(`INSERT INTO forecast_jobs(
      id, harvest_run_id, job_type, status, attempts, created_at, updated_at
    ) VALUES (?, ?, 'PRICE_AND_REVENUE', 'PENDING', 0, ?, ?)
    ON CONFLICT(harvest_run_id, job_type) DO UPDATE SET
      status = CASE WHEN forecast_jobs.status = 'COMPLETED' THEN 'COMPLETED' ELSE 'PENDING' END,
      last_error = NULL, updated_at = excluded.updated_at`)
    .bind(jobId, runId, now, now));
  await env.DB.batch(statements);

  return NextResponse.json({
    runId,
    status: 'FORECAST_QUEUED',
    harvestedCount,
    totalWeightG,
  }, { status: 202 });
}
