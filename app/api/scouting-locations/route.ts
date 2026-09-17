import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { ensureScoutingRuntime } from '@/db/scouting-runtime';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

type ScoutingLocationRow = {
  id: string;
  location_key: string;
  display_location: string | null;
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
  latest_humidity: number | null;
  latest_leaf_temp: number | null;
  latest_ambient_temp: number | null;
  latest_reference_temp: number | null;
  latest_risk_signal: number | null;
  observation_count: number;
};

export async function GET(request: Request) {
  try {
    await ensureSchema();
    await ensureScoutingRuntime();
    const url = new URL(request.url);
    const farmId = url.searchParams.get('farmId')?.trim() ?? '';
    const attentionOnly = url.searchParams.get('attention') !== '0';
    const locationStateId = url.searchParams.get('locationStateId')?.trim() ?? '';
    const requestedLimit = Number(url.searchParams.get('limit') ?? '20');
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(50, Math.floor(requestedLimit))) : 20;
    if (!farmId) return NextResponse.json({ error: '농장을 선택해 주세요.' }, { status: 422 });

    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.viewHistory) {
      return NextResponse.json({ error: '이 농장의 예찰 현황을 볼 권한이 없습니다.' }, { status: 403 });
    }

    const attentionClause = attentionOnly
      ? locationStateId
        ? `AND (s.id = ? OR s.current_state IN ('FIELD_CHECK_REQUIRED', 'SUSPECTED', 'CONFIRMED'))`
        : `AND s.current_state IN ('FIELD_CHECK_REQUIRED', 'SUSPECTED', 'CONFIRMED')`
      : locationStateId ? 'AND s.id = ?' : '';

    const statement = env.DB.prepare(`SELECT
        s.id,
        s.location_key,
        COALESCE(NULLIF(REPLACE(TRIM(s.location_key), ':', '-'), ''), NULLIF(TRIM(s.zone_code), ''), NULLIF(TRIM(s.bed_code), ''), NULLIF(TRIM(s.house_code), '')) AS display_location,
        s.house_code,
        s.bed_code,
        s.zone_code,
        s.current_state,
        s.active_case_id,
        s.last_observed_at,
        s.last_field_check_at,
        s.last_action_at,
        s.last_alert_at,
        s.last_alert_reason,
        c.primary_issue_code,
        c.issue_family,
        c.status AS case_status,
        o.humidity AS latest_humidity,
        o.leaf_temp AS latest_leaf_temp,
        o.ambient_temp AS latest_ambient_temp,
        o.reference_temp AS latest_reference_temp,
        o.risk_signal AS latest_risk_signal,
        (SELECT COUNT(*)
          FROM scouting_observations oc
          WHERE oc.location_state_id = s.id
            AND (s.active_case_id IS NULL OR oc.case_id = s.active_case_id)
        ) AS observation_count
      FROM scouting_location_states s
      LEFT JOIN scouting_cases c ON c.id = s.active_case_id
      LEFT JOIN scouting_observations o ON o.id = (
        SELECT o2.id
        FROM scouting_observations o2
        WHERE o2.location_state_id = s.id
        ORDER BY o2.observed_at DESC, o2.created_at DESC
        LIMIT 1
      )
      WHERE s.farm_id = ? ${attentionClause}
      ORDER BY CASE WHEN s.id = ? THEN 0 ELSE 1 END,
        CASE s.current_state
          WHEN 'FIELD_CHECK_REQUIRED' THEN 1
          WHEN 'CONFIRMED' THEN 2
          WHEN 'SUSPECTED' THEN 3
          WHEN 'POST_TREATMENT' THEN 4
          WHEN 'MONITORING' THEN 5
          WHEN 'WATCH' THEN 6
          ELSE 7 END,
        COALESCE(s.last_alert_at, s.last_observed_at, s.updated_at) DESC
      LIMIT ?`);
    const result = locationStateId
      ? await statement.bind(farmId, locationStateId, locationStateId, limit).all<ScoutingLocationRow>()
      : await statement.bind(farmId, '', limit).all<ScoutingLocationRow>();

    const counts = await env.DB.prepare(`SELECT current_state, COUNT(*) AS count
      FROM scouting_location_states WHERE farm_id = ? GROUP BY current_state`)
      .bind(farmId).all<{ current_state: string; count: number }>();

    return NextResponse.json({
      rows: result.results.map((row) => ({ ...row, observation_count: Number(row.observation_count ?? 0) })),
      counts: Object.fromEntries(counts.results.map((row) => [row.current_state, Number(row.count)])),
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '예찰 구역 현황을 불러오지 못했습니다.' }, { status: 400 });
  }
}
