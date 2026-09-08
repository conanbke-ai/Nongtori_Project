import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember, type FarmMember } from '@/app/lib/farm-auth';
import { normalizeFarmRole, roleLabel, type FarmRole } from '@/app/lib/farm-permissions';

export const runtime = 'edge';

type MemberRow = {
  id: string;
  farm_id: string;
  email: string | null;
  display_name: string | null;
  phone: string | null;
  phone_verified_at: string | null;
  notifications_enabled: number;
  preferred_language: string;
  role: string;
  status: string;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

function value(value: unknown, max: number) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (text.length > max) throw new Error('입력한 내용을 조금 줄여 주세요.');
  return text;
}

function memberName(member: Pick<FarmMember, 'displayName' | 'email' | 'loginId' | 'roleLabel'>) {
  return member.displayName || member.email || member.loginId || member.roleLabel;
}

function targetName(target: MemberRow) {
  return target.display_name || target.email || roleLabel(normalizeFarmRole(target.role));
}

function canManageTarget(actor: FarmMember, target: MemberRow, nextRole?: FarmRole) {
  const targetRole = normalizeFarmRole(target.role);
  if (!actor.permissions.manageMembers || targetRole === 'ADMIN' || actor.id === target.id) return false;
  if (actor.role === 'OWNER') return targetRole === 'WORKER' && (!nextRole || nextRole === 'WORKER');
  return !nextRole || nextRole === 'OWNER' || nextRole === 'WORKER';
}

async function actorFor(request: Request, farmId: string) {
  const actor = await getFarmMember(request, farmId);
  return actor?.permissions.manageMembers ? actor : null;
}

function auditStatement(
  actor: FarmMember,
  target: { id: string; name: string },
  eventType: string,
  detail: Record<string, unknown>,
) {
  return env.DB.prepare(`INSERT INTO farm_member_events(
    id, farm_id, target_member_id, actor_member_id, target_name_snapshot,
    actor_name_snapshot, event_type, detail_json, created_at
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(crypto.randomUUID(), actor.farmId, target.id, actor.id, target.name,
      memberName(actor), eventType, JSON.stringify(detail), new Date().toISOString());
}

export async function GET(request: Request) {
  await ensureSchema();
  const farmId = new URL(request.url).searchParams.get('farmId')?.trim() ?? '';
  const actor = await actorFor(request, farmId);
  if (!actor) return NextResponse.json({ error: '사용자 정보를 관리할 권한이 없습니다.' }, { status: 403 });
  const rows = await env.DB.prepare(`SELECT id, farm_id, email, display_name, phone, phone_verified_at,
      notifications_enabled, preferred_language, role, status, approved_at, created_at, updated_at
    FROM farm_members WHERE farm_id = ? AND status = 'ACTIVE'
    ORDER BY CASE role WHEN 'ADMIN' THEN 1 WHEN 'OWNER' THEN 2 ELSE 3 END,
      COALESCE(display_name, email), created_at`).bind(farmId).all<MemberRow>();
  return NextResponse.json({
    rows: rows.results.map((row) => ({
      ...row,
      role: normalizeFarmRole(row.role),
      role_label: roleLabel(normalizeFarmRole(row.role)),
      phone_verified: Boolean(row.phone_verified_at),
      notifications_enabled: Boolean(row.notifications_enabled),
      can_manage: canManageTarget(actor, row),
    })),
  });
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = value(body.farmId, 100);
    const email = value(body.email, 200).toLowerCase();
    const displayName = value(body.displayName, 80);
    const requestedRoleInput = value(body.role, 20) || 'WORKER';
    if (!['OWNER', 'WORKER'].includes(requestedRoleInput)) {
      return NextResponse.json({ error: '등록할 사용자 권한을 다시 선택해 주세요.' }, { status: 422 });
    }
    const requestedRole = requestedRoleInput as FarmRole;
    if (!farmId || !displayName || !/^\S+@\S+\.\S+$/.test(email)) {
      return NextResponse.json({ error: '작업자 이름과 로그인 이메일을 확인해 주세요.' }, { status: 422 });
    }
    const actor = await actorFor(request, farmId);
    if (!actor) return NextResponse.json({ error: '작업자를 등록할 권한이 없습니다.' }, { status: 403 });
    if (requestedRole === 'ADMIN' || (actor.role === 'OWNER' && requestedRole !== 'WORKER')) {
      return NextResponse.json({ error: '등록할 수 없는 사용자 권한입니다.' }, { status: 403 });
    }

    const existing = await env.DB.prepare(`SELECT id, farm_id, email, display_name, phone, phone_verified_at,
        notifications_enabled, preferred_language, role, status, approved_at, created_at, updated_at
      FROM farm_members WHERE farm_id = ? AND lower(email) = ? LIMIT 1`)
      .bind(farmId, email).first<MemberRow>();
    if (existing?.status === 'ACTIVE') {
      return NextResponse.json({ error: '이미 이 농장에 등록된 이메일입니다.' }, { status: 409 });
    }

    const now = new Date().toISOString();
    const id = existing?.id ?? crypto.randomUUID();
    const loginId = `${farmId}:${email}`;
    const memberWrite = existing
      ? env.DB.prepare(`UPDATE farm_members SET login_id = ?, identity_provider = 'SITES',
        identity_subject = NULL, email = ?, display_name = ?, role = ?, status = 'ACTIVE',
        invited_by_member_id = ?, approved_at = ?, joined_at = COALESCE(joined_at, ?),
        updated_at = ? WHERE id = ?`)
        .bind(loginId, email, displayName, requestedRole, actor.id, now, now, now, id)
      : env.DB.prepare(`INSERT INTO farm_members(
        id, farm_id, login_id, identity_provider, identity_subject, email, display_name,
        phone, phone_verified_at, notifications_enabled, preferred_language,
        invited_by_member_id, approved_at, joined_at, role, status, created_at, updated_at
      ) VALUES (?, ?, ?, 'SITES', NULL, ?, ?, NULL, NULL, 0, 'ko', ?, ?, ?, ?, 'ACTIVE', ?, ?)`)
        .bind(id, farmId, loginId, email, displayName, actor.id, now, now, requestedRole, now, now);
    await env.DB.batch([
      memberWrite,
      auditStatement(actor, { id, name: displayName }, 'MEMBER_INVITED_AND_APPROVED', { role: requestedRole }),
    ]);
    return NextResponse.json({
      id,
      message: `${displayName} 님을 농장 사용자로 승인했습니다. 로그인 접속 권한은 업체 계정 연결 후 사용할 수 있습니다.`,
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '사용자를 등록하지 못했습니다.' }, { status: 400 });
  }
}

export async function PATCH(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = value(body.farmId, 100);
    const memberId = value(body.memberId, 100);
    const displayName = value(body.displayName, 80);
    const nextRoleInput = value(body.role, 20);
    if (!['OWNER', 'WORKER'].includes(nextRoleInput)) {
      return NextResponse.json({ error: '변경할 사용자 권한을 다시 선택해 주세요.' }, { status: 422 });
    }
    const nextRole = nextRoleInput as FarmRole;
    const actor = await actorFor(request, farmId);
    if (!actor) return NextResponse.json({ error: '사용자 정보를 수정할 권한이 없습니다.' }, { status: 403 });
    const target = await env.DB.prepare(`SELECT id, farm_id, email, display_name, phone, phone_verified_at,
        notifications_enabled, preferred_language, role, status, approved_at, created_at, updated_at
      FROM farm_members WHERE id = ? AND farm_id = ? AND status = 'ACTIVE' LIMIT 1`)
      .bind(memberId, farmId).first<MemberRow>();
    if (!target || !displayName || !canManageTarget(actor, target, nextRole)) {
      return NextResponse.json({ error: '이 사용자의 권한은 수정할 수 없습니다.' }, { status: 403 });
    }
    if (normalizeFarmRole(target.role) === 'OWNER' && nextRole === 'WORKER') {
      const ownerCount = await env.DB.prepare(`SELECT COUNT(*) AS count FROM farm_members
        WHERE farm_id = ? AND role = 'OWNER' AND status = 'ACTIVE'`)
        .bind(farmId).first<{ count: number }>();
      if (Number(ownerCount?.count ?? 0) <= 1) {
        return NextResponse.json({ error: '마지막 사업주 계정의 권한은 변경할 수 없습니다.' }, { status: 409 });
      }
    }
    const previous = { displayName: target.display_name, role: normalizeFarmRole(target.role) };
    await env.DB.batch([
      env.DB.prepare(`UPDATE farm_members SET display_name = ?, role = ?, updated_at = ? WHERE id = ?`)
        .bind(displayName, nextRole, new Date().toISOString(), memberId),
      auditStatement(actor, { id: target.id, name: targetName(target) }, 'MEMBER_UPDATED', {
        previous,
        next: { displayName, role: nextRole },
      }),
    ]);
    return NextResponse.json({ message: '사용자 정보를 수정했습니다.' });
  } catch (error) {
    if (error instanceof Error && error.message.includes('LAST_OWNER_REQUIRED')) {
      return NextResponse.json({ error: '마지막 사업주 계정의 권한은 변경할 수 없습니다.' }, { status: 409 });
    }
    return NextResponse.json({ error: error instanceof Error ? error.message : '사용자 정보를 수정하지 못했습니다.' }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  try {
    await ensureSchema();
    const url = new URL(request.url);
    const farmId = url.searchParams.get('farmId')?.trim() ?? '';
    const memberId = url.searchParams.get('memberId')?.trim() ?? '';
    const actor = await actorFor(request, farmId);
    if (!actor) return NextResponse.json({ error: '작업자 계정을 삭제할 권한이 없습니다.' }, { status: 403 });
    const target = await env.DB.prepare(`SELECT id, farm_id, email, display_name, phone, phone_verified_at,
        notifications_enabled, preferred_language, role, status, approved_at, created_at, updated_at
      FROM farm_members WHERE id = ? AND farm_id = ? AND status = 'ACTIVE' LIMIT 1`)
      .bind(memberId, farmId).first<MemberRow>();
    if (!target || !canManageTarget(actor, target)) {
      return NextResponse.json({ error: '이 계정은 삭제할 수 없습니다.' }, { status: 403 });
    }
    if (normalizeFarmRole(target.role) === 'OWNER') {
      const ownerCount = await env.DB.prepare(`SELECT COUNT(*) AS count FROM farm_members
        WHERE farm_id = ? AND role = 'OWNER' AND status = 'ACTIVE'`).bind(farmId).first<{ count: number }>();
      if (Number(ownerCount?.count ?? 0) <= 1) {
        return NextResponse.json({ error: '마지막 사업주 계정은 삭제할 수 없습니다.' }, { status: 409 });
      }
    }
    const name = targetName(target);
    await env.DB.batch([
      auditStatement(actor, { id: target.id, name }, 'MEMBER_DELETED', { role: normalizeFarmRole(target.role) }),
      env.DB.prepare(`UPDATE notification_outbox SET status = 'CANCELED',
        last_error = '사용자 계정 삭제로 발송 취소'
        WHERE recipient_member_id = ? AND status IN ('PENDING', 'SENDING')`).bind(memberId),
      env.DB.prepare(`DELETE FROM farm_members WHERE id = ? AND farm_id = ?`).bind(memberId, farmId),
    ]);
    return NextResponse.json({
      message: `${name} 계정을 삭제했습니다. 촬영 자료와 현장 확인 기록은 농장 기록으로 유지됩니다.`,
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes('LAST_OWNER_REQUIRED')) {
      return NextResponse.json({ error: '마지막 사업주 계정은 삭제할 수 없습니다.' }, { status: 409 });
    }
    return NextResponse.json({ error: error instanceof Error ? error.message : '작업자 계정을 삭제하지 못했습니다.' }, { status: 400 });
  }
}
