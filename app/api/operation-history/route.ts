import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getAccessibleFarms } from '@/app/api/_lib/farm-access';

export const runtime = 'edge';

const sourceTypes = new Set(['VIDEO_IMPORT', 'PERSONAL_CAPTURE']);
const statuses = new Set(['REGISTERED', 'PROCESSING', 'COMPLETED', 'FAILED', 'UPLOADED_AWAITING_MODEL', 'UPLOADED_AWAITING_FRAME_EXTRACTION']);

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farms = await getAccessibleFarms(request);
  const farmId = url.searchParams.get('farmId')?.trim() ?? farms[0]?.id ?? '';
  if (!farms.some((farm) => farm.id === farmId)) {
    return NextResponse.json({ error: '조회할 수 없는 농장입니다.' }, { status: 403 });
  }

  const itemId = url.searchParams.get('itemId')?.trim() ?? '';
  const from = url.searchParams.get('from')?.trim() ?? '';
  const to = url.searchParams.get('to')?.trim() ?? '';
  const sourceType = url.searchParams.get('sourceType')?.trim() ?? '';
  const status = url.searchParams.get('status')?.trim() ?? '';
  const page = Math.max(1, Number.parseInt(url.searchParams.get('page') ?? '1', 10) || 1);
  const limit = Math.min(100, Math.max(10, Number.parseInt(url.searchParams.get('limit') ?? '30', 10) || 30));

  if ((from && !/^\d{4}-\d{2}-\d{2}$/.test(from)) || (to && !/^\d{4}-\d{2}-\d{2}$/.test(to))
    || (sourceType && !sourceTypes.has(sourceType)) || (status && !statuses.has(status))) {
    return NextResponse.json({ error: '검색 조건이 올바르지 않습니다.' }, { status: 400 });
  }
  if (from && to && from > to) {
    return NextResponse.json({ error: '조회 시작일은 종료일보다 늦을 수 없습니다.' }, { status: 400 });
  }
  if (itemId) {
    const item = await env.DB.prepare(`SELECT id FROM farm_items WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
      .bind(itemId, farmId).first();
    if (!item) return NextResponse.json({ error: '이 농장에 연결되지 않은 품목입니다.' }, { status: 400 });
  }

  const clauses = ['cs.farm_id = ?', "cs.source_type != 'ROBOT'"];
  const bindings: Array<string | number> = [farmId];
  if (itemId) { clauses.push('cs.item_id = ?'); bindings.push(itemId); }
  if (from) { clauses.push('date(datetime(cs.started_at, \'+9 hours\')) >= ?'); bindings.push(from); }
  if (to) { clauses.push('date(datetime(cs.started_at, \'+9 hours\')) <= ?'); bindings.push(to); }
  if (sourceType) { clauses.push('cs.source_type = ?'); bindings.push(sourceType); }
  if (status) { clauses.push('cs.processing_status = ?'); bindings.push(status); }
  const where = clauses.join(' AND ');

  const totalRow = await env.DB.prepare(`SELECT COUNT(*) AS count FROM capture_sessions cs WHERE ${where}`)
    .bind(...bindings).first<{ count: number }>();
  const offset = (page - 1) * limit;
  const rows = await env.DB.prepare(`SELECT cs.id, cs.item_id, cs.capture_mode, cs.source_type, cs.processing_status,
      cs.started_at, cs.ended_at, c.name AS camera_name, h.name AS house_name,
      b.name AS bed_name, z.name AS zone_name, fi.display_name AS item_name,
      ct.display_name_ko AS crop_name, cv.display_name_ko AS cultivar_name
    FROM capture_sessions cs
    LEFT JOIN cameras c ON c.id = cs.camera_id AND c.farm_id = cs.farm_id
    LEFT JOIN houses h ON h.id = cs.house_id AND h.farm_id = cs.farm_id
    LEFT JOIN beds b ON b.id = cs.bed_id AND b.house_id = h.id
    LEFT JOIN zones z ON z.id = cs.zone_id AND z.bed_id = b.id
    LEFT JOIN farm_items fi ON fi.id = cs.item_id
    LEFT JOIN crop_types ct ON ct.code = fi.crop_code
    LEFT JOIN cultivars cv ON cv.code = fi.cultivar_code
    WHERE ${where} ORDER BY cs.started_at DESC LIMIT ? OFFSET ?`)
    .bind(...bindings, limit, offset).all();

  const total = Number(totalRow?.count ?? 0);
  return NextResponse.json({ rows: rows.results, total, page, limit, pageCount: Math.ceil(total / limit) });
}
