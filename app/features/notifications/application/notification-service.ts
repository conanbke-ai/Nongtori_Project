import { env } from 'cloudflare:workers';
import { ensureNotificationRuntime } from '@/db/notification-runtime';

export type NotificationSeverity = 'INFO' | 'NOTICE' | 'WARNING' | 'CRITICAL';

const issueLabels: Record<string, string> = {
  SPIDER_MITE: '응애', APHID: '진딧물', THRIPS: '총채벌레',
  POWDERY_MILDEW: '흰가루병', GRAY_MOLD: '잿빛곰팡이병',
  UNKNOWN_PEST: '해충', UNKNOWN_DISEASE: '병해',
  ENVIRONMENTAL_STRESS: '환경·생리 이상', UNKNOWN: '원인 미확인',
};

const reasonLabels: Record<string, string> = {
  NEW_ANOMALY: '새로운 이상 신호가 감지되었습니다.',
  NEW_FIELD_EVIDENCE: '새로운 현장 정보가 반영되었습니다.',
  WORSENING_TREND: '이상 신호가 이전보다 증가했습니다.',
  SPATIAL_SPREAD: '이상 범위가 확대되었습니다.',
  STALE_PREVIOUS_CHECK: '현장 재확인이 필요한 시점입니다.',
  STALE_OR_CHANGED_PATTERN: '이전과 다른 변화가 감지되었습니다.',
  POST_TREATMENT_REBOUND: '조치 후 이상 신호가 다시 감지되었습니다.',
};

function severityFor(decision: string): NotificationSeverity {
  if (decision === 'ESCALATED') return 'CRITICAL';
  if (decision === 'RECHECK_REQUESTED') return 'WARNING';
  return 'NOTICE';
}

export async function createScoutingAppNotification(input: {
  farmId: string;
  locationStateId: string;
  caseId: string | null;
  locationKey: string;
  issueCode: string | null;
  decision: string;
  reason: string;
  observationId: string;
  createdAt: string;
}) {
  await ensureNotificationRuntime();
  const notificationId = crypto.randomUUID();
  const displayLocation = input.locationKey.replaceAll(':', '-');
  const issue = input.issueCode ? issueLabels[input.issueCode] ?? input.issueCode : '병해충';
  const title = input.decision === 'ESCALATED'
    ? `${displayLocation} 조치 후 다시 확인이 필요합니다`
    : `${displayLocation} 병해충 확인이 필요합니다`;
  const body = `${issue} 의심 · ${reasonLabels[input.reason] ?? '새로운 변화가 감지되었습니다.'}`;
  const payload = JSON.stringify({
    scoutingObservationId: input.observationId,
    locationStateId: input.locationStateId,
    caseId: input.caseId,
    issueCode: input.issueCode,
    decision: input.decision,
    reason: input.reason,
  });

  await env.DB.prepare(`INSERT INTO app_notifications(
      id, farm_id, category, notification_type, severity, title, body,
      entity_type, entity_id, location_state_id, case_id, deep_link_screen, payload_json, created_at
    ) VALUES (?, ?, 'PEST', 'PEST_SCOUTING_ALERT', ?, ?, ?, 'SCOUTING_CASE', ?, ?, ?, 'alerts', ?, ?)`)
    .bind(notificationId, input.farmId, severityFor(input.decision), title, body,
      input.caseId, input.locationStateId, input.caseId, payload, input.createdAt).run();

  const recipients = await env.DB.prepare(`SELECT id FROM farm_members
    WHERE farm_id = ? AND status = 'ACTIVE' ORDER BY created_at`).bind(input.farmId).all<{ id: string }>();
  if (recipients.results.length) {
    await env.DB.batch(recipients.results.map((recipient) => env.DB.prepare(`INSERT OR IGNORE INTO app_notification_recipients(
      id, notification_id, recipient_member_id, read_at, dismissed_at, created_at
    ) VALUES (?, ?, ?, NULL, NULL, ?)`)
      .bind(crypto.randomUUID(), notificationId, recipient.id, input.createdAt)));
  }
  return { notificationId, recipientCount: recipients.results.length };
}
