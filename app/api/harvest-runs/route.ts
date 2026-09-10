import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember, publicMemberName, publicSnapshotName } from '@/app/lib/farm-auth';

export const runtime = 'edge';

type HarvestRunRow = {
  id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  started_by_member_id: string | null;
  started_by_name_snapshot: string | null;
  started_by_role: string | null;
  completed_by_member_id: string | null;
  completed_by_name_snapshot: string | null;
  completed_by_role: string | null;
  note: string;
  harvested_count: number;
  total_weight_g: number;
  item_name: string;
};

function text(value: unknown, max: number) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error('입력한 내용을 조금 줄여 주세요.');
  return result;
}

function reviewerName(member: Awaited<ReturnType<typeof getFarmMember>>) {
  return member ? publicMemberName(member) : '확인자';
}

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farmId = url.searchParams.get('farmId')?.trim() ?? '';
  const itemId = url.searchParams.get('itemId')?.trim() ?? '';
  const from = url.searchParams.get('from')?.trim() ?? '';
  const to = url.searchParams.get('to')?.trim() ?? '';
  const member = await getFarmMember(request, farmId);
  if (!member?.permissions.viewHistory) return NextResponse.json({ error: '수확 일지를 볼 권한이 없습니다.' }, { status: 403 });
  if (!itemId || (from && !/^\d{4}-\d{2}-\d{2}$/.test(from)) || (to && !/^\d{4}-\d{2}-\d{2}$/.test(to))) {
    return NextResponse.json({ error: '조회 조건을 확인해 주세요.' }, { status: 400 });
  }
  const item = await env.DB.prepare(`SELECT id FROM farm_items WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
    .bind(itemId, farmId).first();
  if (!item) return NextResponse.json({ error: '이 농장의 품목이 아닙니다.' }, { status: 404 });
  const clauses = ['hr.farm_id = ?', 'hr.item_id = ?'];
  const bindings: string[] = [farmId, itemId];
  if (from) { clauses.push("date(datetime(hr.started_at, '+9 hours')) >= ?"); bindings.push(from); }
  if (to) { clauses.push("date(datetime(hr.started_at, '+9 hours')) <= ?"); bindings.push(to); }
  const rows = await env.DB.prepare(`SELECT hr.id, hr.status, hr.started_at, hr.completed_at,
      hr.started_by_member_id, hr.started_by_name_snapshot, starter.role AS started_by_role,
      hr.completed_by_member_id, hr.completed_by_name_snapshot, finisher.role AS completed_by_role,
      hr.note,
      hr.harvested_count, hr.total_weight_g, fi.display_name AS item_name
    FROM harvest_runs hr JOIN farm_items fi ON fi.id = hr.item_id
    LEFT JOIN farm_members starter ON starter.id = hr.started_by_member_id
    LEFT JOIN farm_members finisher ON finisher.id = hr.completed_by_member_id
    WHERE ${clauses.join(' AND ')} ORDER BY hr.started_at DESC LIMIT 180`)
    .bind(...bindings).all<HarvestRunRow>();
  return NextResponse.json({
    rows: rows.results.map((row) => {
      const {
        started_by_member_id: startedByMemberId,
        started_by_role: startedByRole,
        completed_by_member_id: completedByMemberId,
        completed_by_role: completedByRole,
        ...publicRow
      } = row;
      return {
        ...publicRow,
        started_by_name_snapshot: row.started_by_name_snapshot || startedByMemberId
          ? publicSnapshotName(row.started_by_name_snapshot, {
            memberId: startedByMemberId,
            farmId,
            role: startedByRole,
          })
          : null,
        completed_by_name_snapshot: row.completed_by_name_snapshot || completedByMemberId
          ? publicSnapshotName(row.completed_by_name_snapshot, {
            memberId: completedByMemberId,
            farmId,
            role: completedByRole,
          })
          : null,
      };
    }),
  });
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const itemId = text(body.itemId, 100);
    const note = text(body.note, 300);
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.uploadMedia) return NextResponse.json({ error: '수확 작업을 시작할 권한이 없습니다.' }, { status: 403 });
    const item = await env.DB.prepare(`SELECT id FROM farm_items WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
      .bind(itemId, farmId).first();
    if (!item) return NextResponse.json({ error: '이 농장의 품목이 아닙니다.' }, { status: 404 });
    const active = await env.DB.prepare(`SELECT id, started_at FROM harvest_runs
      WHERE farm_id = ? AND item_id = ? AND status = 'IN_PROGRESS' ORDER BY started_at DESC LIMIT 1`)
      .bind(farmId, itemId).first<{ id: string; started_at: string }>();
    if (active) return NextResponse.json({
      error: '이미 진행 중인 수확 작업이 있습니다.',
      runId: active.id,
      startedAt: active.started_at,
    }, { status: 409 });
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const inserted = await env.DB.prepare(`INSERT INTO harvest_runs(
      id, farm_id, item_id, camera_id, status, started_at, completed_at,
      started_by_member_id, started_by_name_snapshot, completed_by_member_id,
      completed_by_name_snapshot, note, harvested_count, total_weight_g, created_at, updated_at
    ) SELECT ?, ?, ?, NULL, 'IN_PROGRESS', ?, NULL, ?, ?, NULL, NULL, ?, 0, 0, ?, ?
      WHERE NOT EXISTS (
        SELECT 1 FROM harvest_runs WHERE farm_id = ? AND item_id = ? AND status = 'IN_PROGRESS'
      )`)
      .bind(id, farmId, itemId, now, member.id, reviewerName(member), note, now, now, farmId, itemId).run();
    if (!inserted.meta.changes) {
      return NextResponse.json({ error: '이미 진행 중인 수확 작업이 있습니다.' }, { status: 409 });
    }
    return NextResponse.json({ id, startedAt: now, message: '수확 시작 시간을 기록했습니다.' }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '수확 시작 시간을 기록하지 못했습니다.' }, { status: 400 });
  }
}

export async function PATCH(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const runId = text(body.runId, 100);
    const note = text(body.note, 300);
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.uploadMedia) return NextResponse.json({ error: '수확 작업을 마칠 권한이 없습니다.' }, { status: 403 });
    const run = await env.DB.prepare(`SELECT id, note FROM harvest_runs
      WHERE id = ? AND farm_id = ? AND status = 'IN_PROGRESS' LIMIT 1`)
      .bind(runId, farmId).first<{ id: string; note: string }>();
    if (!run) return NextResponse.json({ error: '진행 중인 수확 작업을 찾지 못했습니다.' }, { status: 404 });
    const now = new Date().toISOString();
    await env.DB.prepare(`UPDATE harvest_runs SET status = 'COMPLETED', completed_at = ?,
      completed_by_member_id = ?, completed_by_name_snapshot = ?, note = ?, updated_at = ?
      WHERE id = ? AND farm_id = ? AND status = 'IN_PROGRESS'`)
      .bind(now, member.id, reviewerName(member), note || run.note, now, runId, farmId).run();
    return NextResponse.json({ completedAt: now, message: '수확 종료 시간을 기록했습니다.' });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '수확 종료 시간을 기록하지 못했습니다.' }, { status: 400 });
  }
}
