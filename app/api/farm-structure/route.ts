import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getAccessibleFarms } from '@/app/api/_lib/farm-access';

export const runtime = 'edge';

type FarmRow = { id: string; code: string; name: string; timezone: string; status: string };
type CultivarRow = { farm_id: string; code: string; name: string; status: string };
type HouseRow = { id: string; farm_id: string; code: string; name: string; status: string };
type BedRow = { id: string; house_id: string; code: string; name: string; status: string };
type ZoneRow = { id: string; bed_id: string; code: string; name: string; status: string };
type CameraRow = {
  id: string; farm_id: string; house_id: string | null; bed_id: string | null; zone_id: string | null;
  code: string; name: string; camera_type: string; source_type: string; status: string;
};

export async function GET(request: Request) {
  await ensureSchema();
  const accessibleFarms = await getAccessibleFarms(request);
  if (accessibleFarms.length === 0) return NextResponse.json({ farms: [], setupRequired: true });
  const placeholders = accessibleFarms.map(() => '?').join(',');
  const [farms, cultivars, houses, beds, zones, cameras] = await Promise.all([
    env.DB.prepare(`SELECT id, code, name, timezone, status FROM farms
      WHERE status != 'ARCHIVED' AND id IN (${placeholders}) ORDER BY name`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<FarmRow>(),
    env.DB.prepare(`SELECT fc.farm_id, c.code, c.display_name_ko AS name, fc.status
      FROM farm_cultivars fc JOIN cultivars c ON c.code = fc.cultivar_code
      WHERE fc.status = 'ACTIVE' AND fc.farm_id IN (${placeholders}) ORDER BY c.display_name_ko`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<CultivarRow>(),
    env.DB.prepare(`SELECT id, farm_id, code, name, status FROM houses
      WHERE status != 'ARCHIVED' AND farm_id IN (${placeholders}) ORDER BY display_order, name`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<HouseRow>(),
    env.DB.prepare(`SELECT b.id, b.house_id, b.code, b.name, b.status FROM beds b JOIN houses h ON h.id = b.house_id
      WHERE b.status != 'ARCHIVED' AND h.farm_id IN (${placeholders}) ORDER BY b.display_order, b.name`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<BedRow>(),
    env.DB.prepare(`SELECT z.id, z.bed_id, z.code, z.name, z.status FROM zones z
      JOIN beds b ON b.id = z.bed_id JOIN houses h ON h.id = b.house_id
      WHERE z.status != 'ARCHIVED' AND h.farm_id IN (${placeholders}) ORDER BY z.display_order, z.name`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<ZoneRow>(),
    env.DB.prepare(`SELECT id, farm_id, house_id, bed_id, zone_id, code, name, camera_type, source_type, status
      FROM cameras WHERE status != 'ARCHIVED' AND farm_id IN (${placeholders}) ORDER BY name`)
      .bind(...accessibleFarms.map((farm) => farm.id)).all<CameraRow>(),
  ]);

  const result = farms.results.map((farm) => ({
    ...farm,
    cultivars: cultivars.results.filter((item) => item.farm_id === farm.id).map((item) => ({
      code: item.code,
      name: item.name,
      status: item.status,
    })),
    houses: houses.results.filter((house) => house.farm_id === farm.id).map((house) => ({
      ...house,
      beds: beds.results.filter((bed) => bed.house_id === house.id).map((bed) => ({
        ...bed,
        zones: zones.results.filter((zone) => zone.bed_id === bed.id),
      })),
    })),
    cameras: cameras.results.filter((camera) => camera.farm_id === farm.id),
  }));

  return NextResponse.json({
    farms: result,
    setupRequired: result.length === 0,
    inputPolicy: 'VENDOR_CONFIGURES_STRUCTURE_USERS_NEVER_TYPE_INTERNAL_IDS',
  });
}
