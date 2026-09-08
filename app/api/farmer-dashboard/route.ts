import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import {
  getFarmMember,
  publicMemberAccountCode,
  publicMemberName,
  publicSnapshotName,
} from '@/app/lib/farm-auth';
import type { FarmPermissions } from '@/app/lib/farm-permissions';

export const runtime = 'edge';

type FarmRow = { id: string; name: string; timezone: string };
type AlertRow = {
  id: string;
  item_id: string | null;
  item_name: string | null;
  crop_name: string | null;
  cultivar_name: string | null;
  class_label: string;
  confidence: number | null;
  decision_status: string;
  created_at: string;
  house_name: string | null;
  bed_name: string | null;
  zone_name: string | null;
  review_verdict: string | null;
  review_quick_note_code: string | null;
  review_note: string | null;
  review_note_language: string | null;
  reviewer_member_id: string | null;
  reviewer_name: string | null;
  reviewer_role: string | null;
  reviewed_at: string | null;
};

const noPermissions: FarmPermissions = {
  viewRevenue: false,
  manageMembers: false,
  manageFarm: false,
  uploadMedia: false,
  reviewAlerts: false,
  viewHistory: false,
};

const guideQuery = `SELECT cg.id, cg.crop_code,
    ct.display_name_ko AS crop_name, cg.cultivar_code, cg.guide_type, cg.title,
    cg.symptom_summary, cg.risk_summary, cg.prevention_summary, cg.response_summary,
    cg.source_title, cg.source_url, cg.reviewed_at,
    COALESCE((SELECT GROUP_CONCAT(cgs.stage_code)
      FROM crop_guide_stages cgs WHERE cgs.guide_id = cg.id), '') AS stage_codes
  FROM crop_guides cg JOIN crop_types ct ON ct.code = cg.crop_code`;

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const isLocal = ['localhost', '127.0.0.1'].includes(url.hostname);
  const authUserId = request.headers.get('oai-authenticated-user-id')?.trim() ?? '';
  const authEmail = request.headers.get('oai-authenticated-user-email')?.trim().toLowerCase() ?? '';
  const requestedFarmId = url.searchParams.get('farmId')?.trim() ?? '';
  const localDate = url.searchParams.get('date')?.trim() ?? '';
  const alertStatus = url.searchParams.get('alertStatus') === 'DONE' ? 'DONE' : 'OPEN';
  const requestedAlertPage = Number(url.searchParams.get('alertPage') ?? '1');
  const alertPage = Number.isFinite(requestedAlertPage) ? Math.max(1, Math.floor(requestedAlertPage)) : 1;
  const alertLimit = 20;
  const alertOffset = (alertPage - 1) * alertLimit;

  const farms = isLocal
    ? await env.DB.prepare(`SELECT id, name, timezone FROM farms WHERE status = 'ACTIVE' ORDER BY name`).all<FarmRow>()
    : await env.DB.prepare(`SELECT DISTINCT f.id, f.name, f.timezone
        FROM farms f JOIN farm_members fm ON fm.farm_id = f.id
        WHERE f.status = 'ACTIVE' AND fm.status = 'ACTIVE'
          AND ((fm.identity_provider = 'SITES'
            AND (fm.identity_subject = ? OR fm.identity_subject = fm.farm_id || ':' || ?))
            OR (fm.email IS NOT NULL AND lower(fm.email) = ?))
        ORDER BY f.name`)
      .bind(authUserId, authUserId, authEmail).all<FarmRow>();
  const selectedFarm = requestedFarmId
    ? farms.results.find((farm) => farm.id === requestedFarmId)
    : farms.results[0];

  if (!selectedFarm) {
    const guideCatalog = await env.DB.prepare(`${guideQuery}
      WHERE cg.status = 'ACTIVE' ORDER BY ct.display_name_ko, cg.display_order, cg.title`).all();
    return NextResponse.json({
      farms: farms.results,
      account: {
        authenticated: isLocal || Boolean(authUserId || authEmail),
        loginId: null,
        email: authEmail || null,
        displayName: null,
        publicName: null,
        accountCode: null,
        phone: null,
        phoneVerified: false,
        notificationsEnabled: false,
        preferredLanguage: 'ko',
        role: null,
        roleLabel: null,
        permissions: noPermissions,
        loginManagedExternally: true,
      },
      selectedFarm: null,
      summary: {
        robotCount: 0,
        todayRecordedSessions: 0,
        alertCount: 0,
        pestBreakdown: [{ code: 'MITE', label: '응애', openCount: 0, capability: 'ACTIVE' }],
        harvestCandidates: 0,
        pendingSessions: 0,
      },
      alertPagination: { status: 'OPEN', page: 1, limit: alertLimit, total: 0, pageCount: 0, openCount: 0, doneCount: 0 },
      pendingSessionsByItem: [],
      cameras: [], alerts: [], recentSessions: [], items: [], guides: guideCatalog.results,
      setupRequired: true,
      membershipRequired: !isLocal && Boolean(authUserId || authEmail),
    });
  }

  const member = await getFarmMember(request, selectedFarm.id);
  if (!member) return NextResponse.json({ error: '이 농장의 사용 권한을 확인할 수 없습니다.' }, { status: 403 });

  const profile = member.id ? await env.DB.prepare(`SELECT phone_verified_at, notifications_enabled
    FROM farm_members WHERE id = ?`).bind(member.id).first<{
      phone_verified_at: string | null;
      notifications_enabled: number | null;
    }>() : null;
  const dateFilter = /^\d{4}-\d{2}-\d{2}$/.test(localDate) ? localDate : new Date().toISOString().slice(0, 10);
  const [cameras, sessions, alerts, items, guides, todayCount, harvestCount, pendingCount, pendingByItem, alertCounts] = await Promise.all([
    env.DB.prepare(`SELECT id, name, camera_type, source_type, status, house_id, bed_id, zone_id,
        connection_status, last_seen_at
      FROM cameras WHERE farm_id = ? AND status != 'ARCHIVED' ORDER BY name`)
      .bind(selectedFarm.id).all(),
    env.DB.prepare(`SELECT cs.id, cs.source_type, cs.processing_status, cs.started_at, cs.ended_at,
        c.name AS camera_name, h.name AS house_name, b.name AS bed_name, z.name AS zone_name
      FROM capture_sessions cs
      LEFT JOIN cameras c ON c.id = cs.camera_id
      LEFT JOIN houses h ON h.id = cs.house_id AND h.farm_id = cs.farm_id
      LEFT JOIN beds b ON b.id = cs.bed_id AND b.house_id = h.id
      LEFT JOIN zones z ON z.id = cs.zone_id AND z.bed_id = b.id
      WHERE cs.farm_id = ? AND cs.source_type != 'ROBOT' ORDER BY cs.started_at DESC LIMIT 10`)
      .bind(selectedFarm.id).all(),
    env.DB.prepare(`SELECT fp.id, cs.item_id, fi.display_name AS item_name,
        ct.display_name_ko AS crop_name, cv.display_name_ko AS cultivar_name,
        fp.class_label, fp.confidence, fp.decision_status, fp.created_at,
        h.name AS house_name, b.name AS bed_name, z.name AS zone_name,
        pre.verdict AS review_verdict, pre.quick_note_code AS review_quick_note_code,
        pre.note AS review_note, pre.note_language AS review_note_language,
        pre.reviewer_member_id,
        pre.reviewer_name_snapshot AS reviewer_name,
        pre.reviewer_role_snapshot AS reviewer_role, pre.created_at AS reviewed_at
      FROM frame_predictions fp
      JOIN inference_runs ir ON ir.id = fp.inference_run_id
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id
      LEFT JOIN farm_items fi ON fi.id = cs.item_id AND fi.farm_id = cs.farm_id
      LEFT JOIN crop_types ct ON ct.code = fi.crop_code
      LEFT JOIN cultivars cv ON cv.code = fi.cultivar_code
      LEFT JOIN houses h ON h.id = cs.house_id AND h.farm_id = cs.farm_id
      LEFT JOIN beds b ON b.id = cs.bed_id AND b.house_id = h.id
      LEFT JOIN zones z ON z.id = cs.zone_id AND z.bed_id = b.id
      LEFT JOIN prediction_review_events pre ON pre.id = (
        SELECT pre2.id FROM prediction_review_events pre2
        JOIN frame_predictions reviewed_fp ON reviewed_fp.id = pre2.frame_prediction_id
        WHERE reviewed_fp.inference_run_id = fp.inference_run_id
          AND ((fp.track_id IS NOT NULL AND reviewed_fp.track_id = fp.track_id)
            OR (fp.track_id IS NULL AND reviewed_fp.id = fp.id))
        ORDER BY pre2.created_at DESC, pre2.id DESC LIMIT 1
      )
      WHERE cs.farm_id = ? AND cs.source_type != 'ROBOT'
        AND fp.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
        AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
        AND fp.id = (
          SELECT fp2.id FROM frame_predictions fp2
          JOIN inference_runs ir2 ON ir2.id = fp2.inference_run_id
          WHERE fp2.inference_run_id = fp.inference_run_id
            AND ((fp.track_id IS NOT NULL AND fp2.track_id = fp.track_id)
              OR (fp.track_id IS NULL AND fp2.id = fp.id))
            AND fp2.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
            AND (upper(ir2.task) LIKE '%MITE%' OR upper(fp2.class_label) LIKE '%MITE%' OR fp2.class_label LIKE '%응애%')
          ORDER BY COALESCE(fp2.confidence, 0) DESC, fp2.created_at, fp2.id LIMIT 1
        )
        AND ((? = 'OPEN' AND (pre.verdict IS NULL OR pre.verdict = 'RECHECK'))
          OR (? = 'DONE' AND pre.verdict IN ('MITE_CONFIRMED', 'NOT_MITE')))
      ORDER BY CASE WHEN pre.verdict IS NULL OR pre.verdict = 'RECHECK' THEN 0 ELSE 1 END,
        fp.created_at DESC, fp.id DESC LIMIT ? OFFSET ?`)
      .bind(selectedFarm.id, alertStatus, alertStatus, alertLimit, alertOffset).all<AlertRow>(),
    env.DB.prepare(`SELECT fi.id, fi.crop_code, ct.display_name_ko AS crop_name,
        fi.cultivar_code, c.display_name_ko AS cultivar_name, fi.display_name,
        cp.image_uri AS crop_image_uri, cp.description_ko AS crop_description
      FROM farm_items fi JOIN crop_types ct ON ct.code = fi.crop_code
      LEFT JOIN cultivars c ON c.code = fi.cultivar_code
      LEFT JOIN crop_profiles cp ON cp.crop_code = fi.crop_code
      WHERE fi.farm_id = ? AND fi.status = 'ACTIVE' ORDER BY fi.display_name`)
      .bind(selectedFarm.id).all(),
    env.DB.prepare(`${guideQuery}
      WHERE cg.status = 'ACTIVE' AND cg.crop_code IN (
        SELECT DISTINCT crop_code FROM farm_items WHERE farm_id = ? AND status = 'ACTIVE'
      ) ORDER BY cg.crop_code, cg.display_order, cg.title`)
      .bind(selectedFarm.id).all(),
    env.DB.prepare(`SELECT COUNT(*) AS count FROM capture_sessions
      WHERE farm_id = ? AND source_type IN ('VIDEO_IMPORT', 'PERSONAL_CAPTURE')
        AND date(datetime(created_at, '+9 hours')) = ?`)
      .bind(selectedFarm.id, dateFilter).first<{ count: number }>(),
    env.DB.prepare(`SELECT COUNT(DISTINCT COALESCE(fp.inference_run_id || ':' || fp.track_id, fp.id)) AS count
      FROM frame_predictions fp
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id
      WHERE cs.farm_id = ? AND cs.source_type != 'ROBOT'
        AND fp.class_label IN ('HARVEST_READY', 'RIPE_FRUIT')
        AND fp.decision_status IN ('CONFIRMED', 'AUTO_ACCEPTED')
        AND date(datetime(fp.created_at, '+9 hours')) = ?`)
      .bind(selectedFarm.id, dateFilter).first<{ count: number }>(),
    env.DB.prepare(`SELECT COUNT(*) AS count FROM capture_sessions
      WHERE farm_id = ? AND source_type != 'ROBOT'
        AND processing_status IN ('REGISTERED', 'PROCESSING', 'UPLOADED_AWAITING_MODEL', 'UPLOADED_AWAITING_FRAME_EXTRACTION')`)
      .bind(selectedFarm.id).first<{ count: number }>(),
    env.DB.prepare(`SELECT item_id, COUNT(*) AS count FROM capture_sessions
      WHERE farm_id = ? AND source_type != 'ROBOT'
        AND processing_status IN ('REGISTERED', 'PROCESSING', 'UPLOADED_AWAITING_MODEL', 'UPLOADED_AWAITING_FRAME_EXTRACTION')
        AND date(datetime(started_at, '+9 hours')) BETWEEN date(?, '-30 days') AND ?
      GROUP BY item_id`)
      .bind(selectedFarm.id, dateFilter, dateFilter).all<{ item_id: string | null; count: number }>(),
    env.DB.prepare(`SELECT
        SUM(CASE WHEN pre.verdict IS NULL OR pre.verdict = 'RECHECK' THEN 1 ELSE 0 END) AS open_count,
        SUM(CASE WHEN pre.verdict IN ('MITE_CONFIRMED', 'NOT_MITE') THEN 1 ELSE 0 END) AS done_count
      FROM frame_predictions fp
      JOIN inference_runs ir ON ir.id = fp.inference_run_id
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id
      LEFT JOIN prediction_review_events pre ON pre.id = (
        SELECT pre2.id FROM prediction_review_events pre2
        JOIN frame_predictions reviewed_fp ON reviewed_fp.id = pre2.frame_prediction_id
        WHERE reviewed_fp.inference_run_id = fp.inference_run_id
          AND ((fp.track_id IS NOT NULL AND reviewed_fp.track_id = fp.track_id)
            OR (fp.track_id IS NULL AND reviewed_fp.id = fp.id))
        ORDER BY pre2.created_at DESC, pre2.id DESC LIMIT 1
      )
      WHERE cs.farm_id = ? AND cs.source_type != 'ROBOT'
        AND fp.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
        AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
        AND fp.id = (
          SELECT fp2.id FROM frame_predictions fp2
          JOIN inference_runs ir2 ON ir2.id = fp2.inference_run_id
          WHERE fp2.inference_run_id = fp.inference_run_id
            AND ((fp.track_id IS NOT NULL AND fp2.track_id = fp.track_id)
              OR (fp.track_id IS NULL AND fp2.id = fp.id))
            AND fp2.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
            AND (upper(ir2.task) LIKE '%MITE%' OR upper(fp2.class_label) LIKE '%MITE%' OR fp2.class_label LIKE '%응애%')
          ORDER BY COALESCE(fp2.confidence, 0) DESC, fp2.created_at, fp2.id LIMIT 1
        )`)
      .bind(selectedFarm.id).first<{ open_count: number | null; done_count: number | null }>(),
  ]);

  let revenueForecasts: unknown[] | undefined;
  let forecastJobs: unknown[] | undefined;
  if (member.permissions.viewRevenue) {
    const [forecastResult, jobResult] = await Promise.all([
      env.DB.prepare(`SELECT rf.id, rf.harvest_run_id, hr.item_id, hr.completed_at,
          hr.harvested_count, hr.total_weight_g, rf.grade_breakdown_json,
          rf.estimated_gross_won, rf.estimated_cost_won, rf.estimated_net_won,
          rf.revenue_p10_won, rf.revenue_p90_won, rf.price_basis_date,
          rf.price_model_name, rf.price_model_version, rf.status, rf.generated_at
        FROM revenue_forecasts rf JOIN harvest_runs hr ON hr.id = rf.harvest_run_id
        WHERE hr.farm_id = ? ORDER BY rf.generated_at DESC LIMIT 30`)
        .bind(selectedFarm.id).all(),
      env.DB.prepare(`SELECT fj.id, fj.harvest_run_id, hr.item_id, fj.status, fj.created_at
        FROM forecast_jobs fj JOIN harvest_runs hr ON hr.id = fj.harvest_run_id
        WHERE hr.farm_id = ? AND fj.status IN ('PENDING', 'PROCESSING', 'FAILED')
        ORDER BY fj.created_at DESC LIMIT 30`)
        .bind(selectedFarm.id).all(),
    ]);
    revenueForecasts = forecastResult.results;
    forecastJobs = jobResult.results;
  }

  const safeAlerts = alerts.results.map((alert) => {
    const { reviewer_member_id: reviewerMemberId, ...publicAlert } = alert;
    return {
      ...publicAlert,
      reviewer_name: alert.reviewed_at
        ? publicSnapshotName(alert.reviewer_name, {
          memberId: reviewerMemberId,
          farmId: selectedFarm.id,
          role: alert.reviewer_role,
        })
        : null,
    };
  });

  const openAlertCount = Number(alertCounts?.open_count ?? 0);
  const doneAlertCount = Number(alertCounts?.done_count ?? 0);
  const selectedAlertTotal = alertStatus === 'OPEN' ? openAlertCount : doneAlertCount;
  const response: Record<string, unknown> = {
    farms: farms.results,
    account: {
      authenticated: true,
      loginId: member.loginId,
      email: member.email ?? (authEmail || null),
      displayName: member.displayName,
      publicName: publicMemberName(member),
      accountCode: publicMemberAccountCode(member),
      phone: member.phone,
      phoneVerified: Boolean(profile?.phone_verified_at),
      notificationsEnabled: Boolean(profile?.notifications_enabled),
      preferredLanguage: member.preferredLanguage,
      role: member.role,
      roleLabel: member.roleLabel,
      permissions: member.permissions,
      loginManagedExternally: true,
    },
    selectedFarm,
    summary: {
      robotCount: cameras.results.filter((camera) => camera.source_type === 'ROBOT').length,
      todayRecordedSessions: Number(todayCount?.count ?? 0),
      alertCount: openAlertCount,
      pestBreakdown: [{
        code: 'MITE',
        label: '응애',
        openCount: openAlertCount,
        capability: 'ACTIVE',
      }],
      harvestCandidates: Number(harvestCount?.count ?? 0),
      pendingSessions: Number(pendingCount?.count ?? 0),
    },
    alertPagination: {
      status: alertStatus,
      page: alertPage,
      limit: alertLimit,
      total: selectedAlertTotal,
      pageCount: Math.ceil(selectedAlertTotal / alertLimit),
      openCount: openAlertCount,
      doneCount: doneAlertCount,
    },
    cameras: cameras.results,
    alerts: safeAlerts,
    recentSessions: sessions.results,
    pendingSessionsByItem: pendingByItem.results,
    items: items.results,
    guides: guides.results,
    setupRequired: false,
    membershipRequired: false,
  };
  if (member.permissions.viewRevenue) {
    response.revenueForecasts = revenueForecasts;
    response.forecastJobs = forecastJobs;
  }
  return NextResponse.json(response);
}
