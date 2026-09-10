import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { isLocalRequest } from '@/app/api/_lib/farm-access';

export const runtime = 'edge';

type ForecastResultInput = {
  jobId?: unknown;
  harvestRunId?: unknown;
  targetDate?: unknown;
  horizonDays?: unknown;
  modelName?: unknown;
  modelVersion?: unknown;
  predictions?: unknown;
};

type GradeRow = { grade_code: string; fruit_count: number; total_weight_g: number };
type Prediction = { gradeCode?: unknown; p10?: unknown; p50?: unknown; p90?: unknown };

function workerAuthorized(request: Request) {
  if (isLocalRequest(request)) return true;
  const bindings = env as typeof env & { FORECAST_WORKER_TOKEN?: string };
  return Boolean(bindings.FORECAST_WORKER_TOKEN)
    && request.headers.get('authorization') === `Bearer ${bindings.FORECAST_WORKER_TOKEN}`;
}

export async function POST(request: Request) {
  await ensureSchema();
  if (!workerAuthorized(request)) return NextResponse.json({ error: '예측 작업자 인증에 실패했습니다.' }, { status: 401 });

  const models = await env.DB.prepare(`SELECT model_name, model_version, algorithm, metrics_json, artifact_uri
      FROM forecast_model_registry WHERE status = 'ACTIVE' ORDER BY deployed_at DESC`).all();
  if (models.results.length === 0) {
    return NextResponse.json({ error: '운영 승인된 시세 예측 모델이 아직 없습니다.' }, { status: 409 });
  }

  const job = await env.DB.prepare(`SELECT fj.id, fj.harvest_run_id, hr.farm_id, hr.item_id,
      hr.completed_at, hr.harvested_count, hr.total_weight_g, fi.crop_code, fi.cultivar_code
    FROM forecast_jobs fj
    JOIN harvest_runs hr ON hr.id = fj.harvest_run_id
    JOIN farm_items fi ON fi.id = hr.item_id
    WHERE fj.status = 'PENDING' AND fj.job_type = 'PRICE_AND_REVENUE'
    ORDER BY fj.created_at LIMIT 1`).first<{
      id: string; harvest_run_id: string; farm_id: string; item_id: string; completed_at: string;
      harvested_count: number; total_weight_g: number; crop_code: string; cultivar_code: string | null;
    }>();
  if (!job) return new NextResponse(null, { status: 204 });

  const claimedAt = new Date().toISOString();
  const claim = await env.DB.prepare(`UPDATE forecast_jobs SET status = 'PROCESSING',
      attempts = attempts + 1, updated_at = ? WHERE id = ? AND status = 'PENDING'`)
    .bind(claimedAt, job.id).run();
  if (!claim.meta.changes) return new NextResponse(null, { status: 204 });

  const grades = await env.DB.prepare(`SELECT grade_code, fruit_count, total_weight_g
      FROM harvest_grade_summaries WHERE harvest_run_id = ? ORDER BY grade_code`)
    .bind(job.harvest_run_id).all<GradeRow>();

  return NextResponse.json({ job, grades: grades.results, activeModels: models.results });
}

export async function PUT(request: Request) {
  await ensureSchema();
  if (!workerAuthorized(request)) return NextResponse.json({ error: '예측 작업자 인증에 실패했습니다.' }, { status: 401 });

  let body: ForecastResultInput;
  try { body = await request.json() as ForecastResultInput; }
  catch { return NextResponse.json({ error: 'JSON 요청 형식이 올바르지 않습니다.' }, { status: 400 }); }

  const jobId = typeof body.jobId === 'string' ? body.jobId.trim() : '';
  const harvestRunId = typeof body.harvestRunId === 'string' ? body.harvestRunId.trim() : '';
  const targetDate = typeof body.targetDate === 'string' ? body.targetDate.trim() : '';
  const modelName = typeof body.modelName === 'string' ? body.modelName.trim() : '';
  const modelVersion = typeof body.modelVersion === 'string' ? body.modelVersion.trim() : '';
  const horizonDays = Number(body.horizonDays);
  const predictions = (Array.isArray(body.predictions) ? body.predictions as Prediction[] : []).map((prediction) => ({
    gradeCode: typeof prediction.gradeCode === 'string' ? prediction.gradeCode.trim().toUpperCase() : '',
    p10: Number(prediction.p10), p50: Number(prediction.p50), p90: Number(prediction.p90),
  }));
  const invalidPrediction = predictions.some((prediction) => !prediction.gradeCode
    || !Number.isFinite(prediction.p10) || !Number.isFinite(prediction.p50) || !Number.isFinite(prediction.p90)
    || prediction.p10 < 0 || prediction.p10 > prediction.p50 || prediction.p50 > prediction.p90);
  if (!jobId || !harvestRunId || !/^\d{4}-\d{2}-\d{2}$/.test(targetDate) || !modelName || !modelVersion
    || !Number.isInteger(horizonDays) || horizonDays < 1 || horizonDays > 30 || predictions.length === 0 || invalidPrediction) {
    return NextResponse.json({ error: '예측 결과 형식이 올바르지 않습니다.' }, { status: 400 });
  }

  const job = await env.DB.prepare(`SELECT fj.status, hr.farm_id, hr.item_id, hr.completed_at,
      hr.harvested_count, hr.total_weight_g, fi.crop_code, fi.cultivar_code
    FROM forecast_jobs fj JOIN harvest_runs hr ON hr.id = fj.harvest_run_id
    JOIN farm_items fi ON fi.id = hr.item_id
    WHERE fj.id = ? AND fj.harvest_run_id = ? AND fj.job_type = 'PRICE_AND_REVENUE'`)
    .bind(jobId, harvestRunId).first<{
      status: string; farm_id: string; item_id: string; completed_at: string; harvested_count: number;
      total_weight_g: number; crop_code: string; cultivar_code: string | null;
    }>();
  if (!job || !['PENDING', 'PROCESSING'].includes(job.status)) {
    return NextResponse.json({ error: '처리 가능한 예측 작업을 찾지 못했습니다.' }, { status: 409 });
  }
  const model = await env.DB.prepare(`SELECT id FROM forecast_model_registry
      WHERE model_name = ? AND model_version = ? AND status = 'ACTIVE'`)
    .bind(modelName, modelVersion).first();
  if (!model) return NextResponse.json({ error: '운영 승인된 모델 버전이 아닙니다.' }, { status: 409 });

  const gradeRows = (await env.DB.prepare(`SELECT grade_code, fruit_count, total_weight_g
      FROM harvest_grade_summaries WHERE harvest_run_id = ? ORDER BY grade_code`)
    .bind(harvestRunId).all<GradeRow>()).results;
  const predictionMap = new Map(predictions.map((prediction) => [prediction.gradeCode, prediction]));
  if (gradeRows.length === 0 || gradeRows.some((grade) => !predictionMap.has(grade.grade_code))) {
    return NextResponse.json({ error: '수확 등급별 예측값이 모두 필요합니다.' }, { status: 400 });
  }

  const setting = await env.DB.prepare(`SELECT commission_rate, packaging_won_per_kg,
      labor_won_per_kg, shipping_won_per_kg FROM farm_revenue_settings
    WHERE farm_id = ? AND item_id = ? AND status = 'ACTIVE' LIMIT 1`)
    .bind(job.farm_id, job.item_id).first<{
      commission_rate: number; packaging_won_per_kg: number; labor_won_per_kg: number; shipping_won_per_kg: number;
    }>();

  const breakdown = gradeRows.map((grade) => {
    const prediction = predictionMap.get(grade.grade_code)!;
    return {
      grade: grade.grade_code,
      count: grade.fruit_count,
      weight_g: grade.total_weight_g,
      predicted_price_per_kg: prediction.p50,
      price_p10_per_kg: prediction.p10,
      price_p90_per_kg: prediction.p90,
    };
  });
  const gross = breakdown.reduce((sum, grade) => sum + grade.weight_g / 1000 * grade.predicted_price_per_kg, 0);
  const revenueP10 = breakdown.reduce((sum, grade) => sum + grade.weight_g / 1000 * grade.price_p10_per_kg, 0);
  const revenueP90 = breakdown.reduce((sum, grade) => sum + grade.weight_g / 1000 * grade.price_p90_per_kg, 0);
  const totalKg = job.total_weight_g / 1000;
  const variableWonPerKg = setting ? setting.packaging_won_per_kg + setting.labor_won_per_kg + setting.shipping_won_per_kg : 0;
  const estimatedCost = setting ? gross * setting.commission_rate + totalKg * variableWonPerKg : 0;
  const now = new Date().toISOString();
  const statements: D1PreparedStatement[] = [];
  for (const grade of breakdown) {
    statements.push(env.DB.prepare(`INSERT INTO price_forecasts(
        id, crop_code, cultivar_code, grade_code, target_date, horizon_days, model_name, model_version,
        price_p10_per_kg, price_p50_per_kg, price_p90_per_kg, feature_snapshot_json, status, generated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?)`)
      .bind(crypto.randomUUID(), job.crop_code, job.cultivar_code, grade.grade, targetDate, horizonDays,
        modelName, modelVersion, grade.price_p10_per_kg, grade.predicted_price_per_kg, grade.price_p90_per_kg,
        JSON.stringify({ harvestRunId, itemId: job.item_id }), now));
  }
  statements.push(env.DB.prepare(`INSERT INTO revenue_forecasts(
      id, harvest_run_id, grade_breakdown_json, estimated_gross_won, estimated_cost_won,
      estimated_net_won, revenue_p10_won, revenue_p90_won, price_basis_date,
      price_model_name, price_model_version, status, generated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(harvest_run_id) DO UPDATE SET
      grade_breakdown_json = excluded.grade_breakdown_json, estimated_gross_won = excluded.estimated_gross_won,
      estimated_cost_won = excluded.estimated_cost_won, estimated_net_won = excluded.estimated_net_won,
      revenue_p10_won = excluded.revenue_p10_won, revenue_p90_won = excluded.revenue_p90_won,
      price_basis_date = excluded.price_basis_date, price_model_name = excluded.price_model_name,
      price_model_version = excluded.price_model_version, status = excluded.status, generated_at = excluded.generated_at`)
    .bind(crypto.randomUUID(), harvestRunId, JSON.stringify(breakdown), gross, estimatedCost, gross - estimatedCost,
      revenueP10 - estimatedCost, revenueP90 - estimatedCost, targetDate, modelName, modelVersion,
      setting ? 'COMPLETED' : 'PRICE_ONLY', now));
  statements.push(env.DB.prepare(`UPDATE forecast_jobs SET status = 'COMPLETED', last_error = NULL,
      updated_at = ? WHERE id = ?`).bind(now, jobId));
  await env.DB.batch(statements);

  return NextResponse.json({ harvestRunId, status: setting ? 'COMPLETED' : 'PRICE_ONLY' });
}
