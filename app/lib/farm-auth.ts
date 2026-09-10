import { env } from 'cloudflare:workers';
import {
  can,
  normalizeFarmRole,
  permissionsForRole,
  roleLabel,
  type FarmPermissions,
  type FarmRole,
} from './farm-permissions';

export type FarmMember = {
  id: string | null;
  farmId: string;
  loginId: string;
  identitySubject: string | null;
  email: string | null;
  displayName: string | null;
  phone: string | null;
  preferredLanguage: string;
  role: FarmRole;
  roleLabel: string;
  permissions: FarmPermissions;
};

type PublicAccountIdentity = {
  id?: string | null;
  farmId?: string | null;
  loginId?: string | null;
  role?: unknown;
};

type PublicMemberIdentity = Pick<
  FarmMember,
  'id' | 'farmId' | 'loginId' | 'displayName' | 'role' | 'roleLabel'
>;

type PublicSnapshotIdentity = {
  accountCode?: string | null;
  memberId?: string | null;
  farmId?: string | null;
  role?: unknown;
};

function nonEmailLabel(value: string | null | undefined) {
  const label = value?.trim() ?? '';
  return label && !label.includes('@') ? label : '';
}

function normalizedPublicRole(value: unknown): FarmRole | null {
  return value === 'ADMIN' || value === 'OWNER' || value === 'WORKER' ? value : null;
}

function shortAccountCode(source: string) {
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36).toUpperCase().padStart(4, '0').slice(-4);
}

export function publicMemberAccountCode(member: PublicAccountIdentity) {
  const role = normalizedPublicRole(member.role);
  const prefix = role === 'ADMIN' ? 'A' : role === 'OWNER' ? 'O' : role === 'WORKER' ? 'W' : 'U';
  const source = member.id?.trim() || member.loginId?.trim() || member.farmId?.trim() || `${prefix}:anonymous`;
  return `${prefix}-${shortAccountCode(source)}`;
}

/**
 * Shared records must identify a member without exposing their sign-in email.
 * A nickname wins, followed by a non-email login ID. Scoped IDs are shortened
 * to the member-facing part. The final fallback is an anonymous stable code.
 */
export function publicMemberName(member: PublicMemberIdentity) {
  const nickname = nonEmailLabel(member.displayName);
  if (nickname) return nickname;

  const farmPrefix = `${member.farmId}:`;
  const unscopedLoginId = member.loginId.startsWith(farmPrefix)
    ? member.loginId.slice(farmPrefix.length)
    : member.loginId;
  const loginId = nonEmailLabel(unscopedLoginId);
  if (loginId) return loginId;

  return `${member.roleLabel} · ${publicMemberAccountCode(member)}`;
}

/**
 * Sanitizes immutable name snapshots before they cross an API boundary. This
 * protects older rows that may have stored a sign-in email as the display name.
 */
export function publicSnapshotName(
  snapshotName: string | null | undefined,
  identity: PublicSnapshotIdentity = {},
) {
  const name = nonEmailLabel(snapshotName);
  if (name) return name;

  const role = normalizedPublicRole(identity.role);
  const suppliedCode = nonEmailLabel(identity.accountCode);
  const accountCode = suppliedCode && /^[AOWU]-[A-Z0-9]{4}$/.test(suppliedCode)
    ? suppliedCode
    : publicMemberAccountCode({
      id: identity.memberId,
      farmId: identity.farmId,
      role,
    });
  return accountCode;
}

type FarmMemberRow = {
  id: string;
  farm_id: string;
  login_id: string;
  identity_subject: string | null;
  email: string | null;
  display_name: string | null;
  phone: string | null;
  preferred_language: string | null;
  role: string;
};

export function requestIdentity(request: Request) {
  const url = new URL(request.url);
  const isLocal = ['localhost', '127.0.0.1'].includes(url.hostname);
  return {
    isLocal,
    userId: request.headers.get('oai-authenticated-user-id')?.trim() ?? '',
    email: request.headers.get('oai-authenticated-user-email')?.trim().toLowerCase() ?? '',
  };
}

export function scopedIdentitySubject(farmId: string, identitySubject: string) {
  return identitySubject ? `${farmId}:${identitySubject}` : '';
}

function memberFromRow(row: FarmMemberRow): FarmMember {
  const role = normalizeFarmRole(row.role);
  return {
    id: row.id,
    farmId: row.farm_id,
    loginId: row.login_id,
    identitySubject: row.identity_subject,
    email: row.email,
    displayName: row.display_name,
    phone: row.phone,
    preferredLanguage: row.preferred_language || 'ko',
    role,
    roleLabel: roleLabel(role),
    permissions: permissionsForRole(role),
  };
}

export async function getFarmMember(request: Request, farmId: string): Promise<FarmMember | null> {
  const identity = requestIdentity(request);
  if (identity.isLocal) {
    const localMember = await env.DB.prepare(`SELECT id, farm_id, login_id, identity_subject, email,
        display_name, phone, preferred_language, role
      FROM farm_members WHERE farm_id = ? AND status = 'ACTIVE'
      ORDER BY CASE role WHEN 'ADMIN' THEN 1 WHEN 'OWNER' THEN 2 ELSE 3 END, created_at LIMIT 1`)
      .bind(farmId).first<FarmMemberRow>();
    if (localMember) return memberFromRow(localMember);
    const role: FarmRole = 'ADMIN';
    return {
      id: null,
      farmId,
      loginId: 'local-preview',
      identitySubject: null,
      email: null,
      displayName: '로컬 관리자',
      phone: null,
      preferredLanguage: 'ko',
      role,
      roleLabel: roleLabel(role),
      permissions: permissionsForRole(role),
    };
  }
  if (!identity.userId && !identity.email) return null;
  const scopedSubject = scopedIdentitySubject(farmId, identity.userId);
  const member = await env.DB.prepare(`SELECT id, farm_id, login_id, identity_subject, email,
      display_name, phone, preferred_language, role
    FROM farm_members
    WHERE farm_id = ? AND status = 'ACTIVE'
      AND ((identity_provider = 'SITES' AND identity_subject IN (?, ?))
        OR (email IS NOT NULL AND lower(email) = ?))
    ORDER BY CASE WHEN identity_subject = ? THEN 0 WHEN identity_subject = ? THEN 1 ELSE 2 END LIMIT 1`)
    .bind(farmId, scopedSubject, identity.userId, identity.email, scopedSubject, identity.userId)
    .first<FarmMemberRow>();
  return member ? memberFromRow(member) : null;
}

export async function hasFarmAccess(request: Request, farmId: string) {
  return Boolean(await getFarmMember(request, farmId));
}

export async function hasFarmPermission(
  request: Request,
  farmId: string,
  permission: keyof FarmPermissions,
) {
  const member = await getFarmMember(request, farmId);
  return member ? can(member.role, permission) : false;
}
