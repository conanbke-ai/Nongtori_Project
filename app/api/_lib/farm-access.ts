import { env } from 'cloudflare:workers';
import { requestIdentity } from '@/app/lib/farm-auth';

export type AccessibleFarm = { id: string; name: string; timezone: string };

export async function getAccessibleFarms(request: Request) {
  const identity = requestIdentity(request);
  if (!identity.userId && !identity.email) return [];

  return (await env.DB.prepare(`SELECT DISTINCT f.id, f.name, f.timezone
      FROM farms f JOIN farm_members fm ON fm.farm_id = f.id
      WHERE f.status = 'ACTIVE' AND fm.status = 'ACTIVE'
        AND ((fm.identity_provider = 'SITES'
          AND (fm.identity_subject = ? OR fm.identity_subject = fm.farm_id || ':' || ?))
          OR (fm.email IS NOT NULL AND lower(fm.email) = ?))
      ORDER BY f.name`)
    .bind(identity.userId, identity.userId, identity.email).all<AccessibleFarm>()).results;
}
