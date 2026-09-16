import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

type ScoutingLocationRow = {
  id: string;
  location_key: string;
  house_code: string;
  bed_code: string;
  zone_code: string;
  current_state: string;
  active_case_id: string | null;
  last_observed_at: string | null;
  last_field_check_at: string | null;
  last_action_at: string | null;
  last_alert_at: string | null;
  last_alert_reason: string | null;
  primary_issue_code: string | null;
  issue_family: string | null;
  case_status: string | null;
};

export async function GET(request: Request) {
  try {
    await ensureSchema();
    const url = new URL(request.url);
    const farmId = url.searchParams.get('farmId')?.trim() ?? '';
    const attentionOnly = url.searchParams.get('attention') !== '0';
    const requestedLimit = Number(url.searchParams.get('limit') ?? '20');
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(50, Math.floor(requestedLimit))) : 20;
    if (!farmId) return NextResponse.json({ error: '농장을 선택해 주세요.' }, { status: 422 });

    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.viewHistory) {
      return NextResponse.json({ error: '이 농장의 예찰 현황을 볼 권한이 없습니다.' }, { status: 403 });
    }

    const attentionClause = attentionOnly
      ? `AND s.current_state IN ('FIELD_CHECK_REQUIRED', 'SUSPECTED', 'CONFIRMED', 'POST_TREATMENT', 'MONITORING')`
      : '';
    const result = await env.DB.prepare(`SELECT
        s.id, s.location_key, s.house_code, s.bed_code, s.zone_code, s.current_state,
        s.active_case_id, s.last_observed_at, s.last_field_check_at, s.last_action_at,
        s.last_alert_at, s.last_alert_reason,
        c.primary_issue_code, c.issue_family, c.status AS case_status
      FROM scouting_location_states s
      LEFT JOIN scouting_cases c ON c.id = s.active_case_id
      WHERE s.farm_id = ? ${attentionClause}
      ORDER BY CASE s.current_state
        WHEN 'FIELD_CHECK_REQUIRED' THEN 1
        WHEN 'CONFIRMED' THEN 2
        WHEN 'SUSPECTED' THEN 3
        WHEN 'POST_TREATMENT' THEN 4
        WHEN 'MONITORING' THEN 5
        WHEN 'WATCH' THEN 6
        ELSE 7 END,
        COALESCE(s.last_alert_at, s.last_observed_at, s.updated_at) DESC
      LIMIT ?`)
      .bind(farmId, limit)
      .all<ScoutingLocationRow>();

    const counts = await env.DB.prepare(`SELECT current_state, COUNT(*) AS count
      FROM scouting_location_states WHERE farm_id = ? GROUP BY current_state`)
      .bind(farmId).all<{ current_state: string; count: number }>();

    return NextResponse.json({ rows: result.results, counts: Object.fromEntries(counts.results.map((row) => [row.current_state, Number(row.count)])) });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '예찰 구역 현황을 불러오지 못했습니다.' }, { status: 400 });
  }
}
