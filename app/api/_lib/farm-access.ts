import { env } from 'cloudflare:workers';

export type AccessibleFarm = { id: string; name: string; timezone: string };

export function isLocalRequest(request: Request) {
  return ['localhost', '127.0.0.1'].includes(new URL(request.url).hostname);
}

export async function getAccessibleFarms(request: Request) {
  if (isLocalRequest(request)) {
    return (await env.DB.prepare(
      `SELECT id, name, timezone FROM farms WHERE status = 'ACTIVE' ORDER BY name`,
    ).all<AccessibleFarm>()).results;
  }

  const authUserId = request.headers.get('oai-authenticated-user-id')?.trim() ?? '';
  const authEmail = request.headers.get('oai-authenticated-user-email')?.trim().toLowerCase() ?? '';
  if (!authUserId && !authEmail) return [];

  return (await env.DB.prepare(`SELECT DISTINCT f.id, f.name, f.timezone
      FROM farms f JOIN farm_members fm ON fm.farm_id = f.id
      WHERE f.status = 'ACTIVE' AND fm.status = 'ACTIVE'
        AND ((fm.identity_provider = 'SITES'
          AND (fm.identity_subject = ? OR fm.identity_subject = fm.farm_id || ':' || ?))
          OR (fm.email IS NOT NULL AND lower(fm.email) = ?))
      ORDER BY f.name`)
    .bind(authUserId, authUserId, authEmail).all<AccessibleFarm>()).results;
}
