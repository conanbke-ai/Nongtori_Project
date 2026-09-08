import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';

export const runtime = 'edge';

type NotificationBindings = typeof env & {
  NOTIFICATION_WORKER_TOKEN?: string;
  SMS_ALERT_URL?: string;
  SMS_ALERT_TOKEN?: string;
};

type OutboxRow = {
  id: string;
  recipient_phone: string;
  preferred_language: string;
  farm_name: string;
  house_name: string | null;
  bed_name: string | null;
  zone_name: string | null;
};

function alertMessage(language: string, farmName: string, locationParts: Array<string | null>) {
  const knownLocation = locationParts.filter(Boolean).join(' · ');
  const location = knownLocation || (language === 'vi'
    ? 'cần xác nhận vị trí'
    : language === 'th'
      ? 'กรุณาตรวจสอบตำแหน่ง'
      : language === 'zh-CN'
        ? '位置待确认'
        : '위치 확인 필요');
  if (language === 'vi') return `[Trung tâm vận hành] ${farmName} · ${location}: phát hiện hình ảnh nghi có nhện đỏ. Vui lòng kiểm tra tại vườn.`;
  if (language === 'th') return `[ศูนย์จัดการฟาร์ม] ${farmName} · ${location}: พบภาพที่สงสัยว่ามีไรแดง กรุณาตรวจที่แปลง`;
  if (language === 'zh-CN') return `[农场运营中心] ${farmName} · ${location}：发现疑似螨虫画面，请到现场检查。`;
  return `[농토리 운영센터] ${farmName} ${location}에서 응애 의심 신호가 감지되었습니다. 현장에서 확인해 주세요.`;
}

export async function POST(request: Request) {
  await ensureSchema();
  const bindings = env as NotificationBindings;
  if (!bindings.NOTIFICATION_WORKER_TOKEN || request.headers.get('authorization') !== `Bearer ${bindings.NOTIFICATION_WORKER_TOKEN}`) {
    return NextResponse.json({ error: '알림 발송 작업 인증에 실패했습니다.' }, { status: 401 });
  }
  if (!bindings.SMS_ALERT_URL || !bindings.SMS_ALERT_TOKEN) {
    return NextResponse.json({ error: '문자 알림 발송 서비스가 아직 연결되지 않았습니다.' }, { status: 503 });
  }

  await env.DB.prepare(`UPDATE notification_outbox SET
      status = CASE WHEN attempts >= 5 THEN 'FAILED' ELSE 'PENDING' END,
      claimed_at = NULL,
      last_error = CASE WHEN attempts >= 5 THEN '발송 작업 중단 후 재시도 한도 초과' ELSE last_error END
    WHERE status = 'SENDING'
      AND (claimed_at IS NULL OR julianday(claimed_at) < julianday('now', '-5 minutes'))`).run();

  const pending = await env.DB.prepare(`SELECT no.id, no.recipient_phone, fm.preferred_language, f.name AS farm_name,
      h.name AS house_name, b.name AS bed_name, z.name AS zone_name
    FROM notification_outbox no
    JOIN farms f ON f.id = no.farm_id
    JOIN farm_members fm ON fm.id = no.recipient_member_id
      AND fm.status = 'ACTIVE' AND fm.phone = no.recipient_phone
      AND fm.phone_verified_at IS NOT NULL AND fm.notifications_enabled = 1
    LEFT JOIN frame_predictions fp ON fp.id = no.frame_prediction_id
    LEFT JOIN frames fr ON fr.id = fp.frame_id
    LEFT JOIN capture_sessions cs ON cs.id = fr.capture_session_id
    LEFT JOIN houses h ON h.id = cs.house_id AND h.farm_id = cs.farm_id
    LEFT JOIN beds b ON b.id = cs.bed_id AND b.house_id = h.id
    LEFT JOIN zones z ON z.id = cs.zone_id AND z.bed_id = b.id
    WHERE no.status = 'PENDING' AND no.attempts < 5
    ORDER BY no.created_at LIMIT 20`).all<OutboxRow>();

  let sent = 0;
  let failed = 0;
  for (const row of pending.results) {
    const claimedAt = new Date().toISOString();
    const claimed = await env.DB.prepare(`UPDATE notification_outbox
      SET status = 'SENDING', claimed_at = ?, attempts = attempts + 1
      WHERE id = ? AND status = 'PENDING'`)
      .bind(claimedAt, row.id).run();
    if (!claimed.meta.changes) continue;
    try {
      const response = await fetch(bindings.SMS_ALERT_URL, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${bindings.SMS_ALERT_TOKEN}`,
          'content-type': 'application/json',
          'idempotency-key': row.id,
        },
        signal: AbortSignal.timeout(10_000),
        body: JSON.stringify({
          to: row.recipient_phone,
          type: 'MITE_ALERT',
          message: alertMessage(row.preferred_language, row.farm_name,
            [row.house_name, row.bed_name, row.zone_name]),
        }),
      });
      if (!response.ok) throw new Error(`문자 발송 응답 ${response.status}`);
      await env.DB.prepare(`UPDATE notification_outbox
        SET status = 'SENT', sent_at = ?, claimed_at = NULL, last_error = NULL WHERE id = ?`)
        .bind(new Date().toISOString(), row.id).run();
      sent += 1;
    } catch (error) {
      await env.DB.prepare(`UPDATE notification_outbox SET
          status = CASE WHEN attempts >= 5 THEN 'FAILED' ELSE 'PENDING' END,
          claimed_at = NULL, last_error = ? WHERE id = ?`)
        .bind(error instanceof Error ? error.message.slice(0, 300) : '문자 발송 실패', row.id).run();
      failed += 1;
    }
  }
  return NextResponse.json({ processed: pending.results.length, sent, failed });
}
