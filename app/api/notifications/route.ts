import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { ensureNotificationRuntime } from '@/db/notification-runtime';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

type NotificationRow = {
  recipient_id: string;
  notification_id: string;
  category: string;
  notification_type: string;
  severity: string;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  location_state_id: string | null;
  case_id: string | null;
  deep_link_screen: string | null;
  payload_json: string;
  created_at: string;
  read_at: string | null;
};

async function context(request: Request, farmId: string) {
  await ensureSchema();
  await ensureNotificationRuntime();
  if (!farmId) return { error: NextResponse.json({ error: '농장을 선택해 주세요.' }, { status: 422 }) };
  const member = await getFarmMember(request, farmId);
  if (!member?.permissions.viewHistory) {
    return { error: NextResponse.json({ error: '이 농장의 알림을 볼 권한이 없습니다.' }, { status: 403 }) };
  }
  if (!member.id) return { error: NextResponse.json({ rows: [], unreadCount: 0 }) };
  return { member };
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const farmId = url.searchParams.get('farmId')?.trim() ?? '';
    const requestedLimit = Number(url.searchParams.get('limit') ?? '30');
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(50, Math.floor(requestedLimit))) : 30;
    const resolved = await context(request, farmId);
    if ('error' in resolved) return resolved.error;

    const result = await env.DB.prepare(`SELECT
        r.id AS recipient_id, n.id AS notification_id, n.category, n.notification_type, n.severity,
        n.title, n.body, n.entity_type, n.entity_id, n.location_state_id, n.case_id,
        n.deep_link_screen, n.payload_json, n.created_at, r.read_at
      FROM app_notification_recipients r
      JOIN app_notifications n ON n.id = r.notification_id
      WHERE r.recipient_member_id = ? AND n.farm_id = ? AND r.dismissed_at IS NULL
      ORDER BY n.created_at DESC
      LIMIT ?`)
      .bind(resolved.member.id, farmId, limit).all<NotificationRow>();
    const unread = await env.DB.prepare(`SELECT COUNT(*) AS count
      FROM app_notification_recipients r
      JOIN app_notifications n ON n.id = r.notification_id
      WHERE r.recipient_member_id = ? AND n.farm_id = ?
        AND r.dismissed_at IS NULL AND r.read_at IS NULL`)
      .bind(resolved.member.id, farmId).first<{ count: number }>();
    return NextResponse.json({ rows: result.results, unreadCount: Number(unread?.count ?? 0) });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '알림을 불러오지 못했습니다.' }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as { farmId?: string; action?: string; notificationId?: string };
    const farmId = body.farmId?.trim() ?? '';
    const resolved = await context(request, farmId);
    if ('error' in resolved) return resolved.error;
    const now = new Date().toISOString();

    if (body.action === 'READ_ALL') {
      await env.DB.prepare(`UPDATE app_notification_recipients SET read_at = COALESCE(read_at, ?)
        WHERE recipient_member_id = ? AND dismissed_at IS NULL
          AND notification_id IN (SELECT id FROM app_notifications WHERE farm_id = ?)`)
        .bind(now, resolved.member.id, farmId).run();
      return NextResponse.json({ ok: true });
    }

    const notificationId = body.notificationId?.trim() ?? '';
    if (!notificationId) return NextResponse.json({ error: '알림을 선택해 주세요.' }, { status: 422 });
    const ownership = `recipient_member_id = ? AND notification_id = ?
      AND notification_id IN (SELECT id FROM app_notifications WHERE farm_id = ?)`;
    if (body.action === 'READ') {
      await env.DB.prepare(`UPDATE app_notification_recipients SET read_at = COALESCE(read_at, ?)
        WHERE ${ownership}`).bind(now, resolved.member.id, notificationId, farmId).run();
      return NextResponse.json({ ok: true });
    }
    if (body.action === 'DISMISS') {
      await env.DB.prepare(`UPDATE app_notification_recipients
        SET read_at = COALESCE(read_at, ?), dismissed_at = ? WHERE ${ownership}`)
        .bind(now, now, resolved.member.id, notificationId, farmId).run();
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: '알림 작업을 다시 선택해 주세요.' }, { status: 422 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '알림 상태를 변경하지 못했습니다.' }, { status: 400 });
  }
}
