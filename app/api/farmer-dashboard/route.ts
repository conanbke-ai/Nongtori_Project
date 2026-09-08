import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import {
  getFarmMember,
  publicMemberAccountCode,
  publicMemberName,
  publicSnapshotName,
} from '@/app/lib/farm-auth';
import { pestTargets, findPestTarget } from '@/app/features/pests/domain/catalog';
import { PestRepository } from '@/app/features/pests/infrastructure/pest-repository';
import { loadPestDashboard } from '@/app/features/pests/application/pest-service';
import type { FarmPermissions } from '@/app/lib/farm-permissions';

export const runtime = 'edge';

type FarmRow = { id: string; name: string; timezone: string };
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
  const pestCode = url.searchParams.get('pestCode')?.trim() ?? '';
  if (pestCode && !findPestTarget(pestCode)) return NextResponse.json({ error: '병해충 종류를 확인해 주세요.' }, { status: 422 });

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
        pestBreakdown: pestTargets.map((target) => ({ code: target.code, label: target.labels.ko, openCount: 0, capability: target.capability })),
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
  const [cameras, sessions, items, guides, todayCount, harvestCount, pendingCount, pendingByItem] = await Promise.all([
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

  const pests = await loadPestDashboard(new PestRepository(env.DB), selectedFarm.id, pestCode, alertStatus, alertPage, alertLimit);
  const safeAlerts = pests.rows.map((alert) => {
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
      alertCount: pests.totalOpen,
      pestBreakdown: pests.breakdown,
      harvestCandidates: Number(harvestCount?.count ?? 0),
      pendingSessions: Number(pendingCount?.count ?? 0),
    },
    alertPagination: pests.pagination,
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
