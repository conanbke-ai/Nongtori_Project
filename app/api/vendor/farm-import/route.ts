import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';

export const runtime = 'edge';

type JsonObject = Record<string, unknown>;

function object(value: unknown, name: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${name} 형식이 올바르지 않습니다.`);
  return value as JsonObject;
}

function items(value: unknown) {
  if (value === undefined) return [] as JsonObject[];
  if (!Array.isArray(value)) throw new Error('목록 형식이 올바르지 않습니다.');
  return value.map((item, index) => object(item, `${index + 1}번째 항목`));
}

function text(value: unknown, name: string, required = false, max = 120) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (required && !result) throw new Error(`${name} 값이 필요합니다.`);
  if (result.length > max) throw new Error(`${name} 값이 너무 깁니다.`);
  return result;
}

function code(value: unknown, name: string) {
  const result = text(value, name, true, 60).toUpperCase().replace(/[^A-Z0-9_-]/g, '_');
  if (!result) throw new Error(`${name} 코드를 확인해 주세요.`);
  return result;
}

function order(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? number : fallback;
}

function metadata(value: unknown) {
  return JSON.stringify(value && typeof value === 'object' && !Array.isArray(value) ? value : {});
}

export async function POST(request: Request) {
  try {
    const isLocal = ['localhost', '127.0.0.1'].includes(new URL(request.url).hostname);
    const bindings = env as typeof env & { VENDOR_IMPORT_TOKEN?: string };
    if (!isLocal) {
      if (!bindings.VENDOR_IMPORT_TOKEN) {
        return NextResponse.json({ error: '업체 설정용 보안키가 아직 연결되지 않았습니다.' }, { status: 503 });
      }
      if (request.headers.get('authorization') !== `Bearer ${bindings.VENDOR_IMPORT_TOKEN}`) {
        return NextResponse.json({ error: '업체 관리자 인증에 실패했습니다.' }, { status: 401 });
      }
    }
    const payload = object(await request.json(), '가져오기 자료');
    const source = object(payload.source, '원본 정보');
    const farmInput = object(payload.farm, '농가 정보');
    const sourceType = text(source.type, '원본 종류', true);
    if (!['GOOGLE_SHEET_SNAPSHOT', 'CSV_SNAPSHOT'].includes(sourceType)) {
      throw new Error('읽기 전용 Google Sheets 또는 CSV 스냅샷만 가져올 수 있습니다.');
    }

    const farmCode = code(farmInput.code, '농가');
    const farmName = text(farmInput.name, '농가명', true);
    const timezone = text(farmInput.timezone, '시간대') || 'Asia/Seoul';
    const spreadsheetId = text(source.spreadsheetId, '스프레드시트 ID', false, 160) || null;
    const sheetGid = text(source.sheetGid, '시트 GID', false, 40) || null;
    if (sourceType === 'GOOGLE_SHEET_SNAPSHOT' && !spreadsheetId) throw new Error('스프레드시트 ID가 필요합니다.');

    await ensureSchema();
    const now = new Date().toISOString();
    let created = 0;
    let updated = 0;

    const existingFarm = await env.DB.prepare('SELECT id FROM farms WHERE code = ?').bind(farmCode).first<{ id: string }>();
    const farmId = existingFarm?.id ?? crypto.randomUUID();
    await env.DB.prepare(`INSERT INTO farms(id, code, name, timezone, status, created_at, updated_at)
      VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
      ON CONFLICT(code) DO UPDATE SET name = excluded.name, timezone = excluded.timezone,
        status = 'ACTIVE', updated_at = excluded.updated_at`)
      .bind(farmId, farmCode, farmName, timezone, now, now).run();
    if (existingFarm) updated += 1;
    else created += 1;

    const cultivarInputs = items(payload.cultivars);
    for (const cultivarInput of cultivarInputs) {
      const cultivarCode = code(cultivarInput.code, '품종');
      const cultivarName = text(cultivarInput.name, '품종명', true);
      const existing = await env.DB.prepare('SELECT code FROM cultivars WHERE code = ?').bind(cultivarCode).first();
      await env.DB.prepare(`INSERT INTO cultivars(
        code, display_name_ko, operational_status, supports_quality,
        supports_ripeness, supports_mite_warning, created_at
      ) VALUES (?, ?, 'DATA_COLLECTION', 0, 0, 0, ?)
      ON CONFLICT(code) DO UPDATE SET display_name_ko = excluded.display_name_ko`)
        .bind(cultivarCode, cultivarName, now).run();
      await env.DB.prepare(`INSERT INTO farm_cultivars(id, farm_id, cultivar_code, status, created_at)
        VALUES (?, ?, ?, 'ACTIVE', ?)
        ON CONFLICT(farm_id, cultivar_code) DO UPDATE SET status = 'ACTIVE'`)
        .bind(crypto.randomUUID(), farmId, cultivarCode, now).run();
      const existingItem = await env.DB.prepare(`SELECT id FROM farm_items
        WHERE farm_id = ? AND crop_code = 'STRAWBERRY' AND cultivar_code = ?`)
        .bind(farmId, cultivarCode).first<{ id: string }>();
      await env.DB.prepare(`INSERT INTO farm_items(
        id, farm_id, crop_code, cultivar_code, display_name, status, created_at, updated_at
      ) VALUES (?, ?, 'STRAWBERRY', ?, ?, 'ACTIVE', ?, ?)
      ON CONFLICT(farm_id, crop_code, cultivar_code) DO UPDATE SET
        display_name = excluded.display_name, status = 'ACTIVE', updated_at = excluded.updated_at`)
        .bind(existingItem?.id ?? crypto.randomUUID(), farmId, cultivarCode, `${cultivarName} 딸기`, now, now).run();
      if (existing) updated += 1;
      else created += 1;
    }

    for (const itemInput of items(payload.items)) {
      const cropCode = code(itemInput.cropCode, '품목');
      const cropName = text(itemInput.cropName, '품목명', true);
      const cultivarCode = itemInput.cultivarCode ? code(itemInput.cultivarCode, '품종') : null;
      const cultivarName = text(itemInput.cultivarName, '품종명');
      await env.DB.prepare(`INSERT INTO crop_types(code, display_name_ko, created_at)
        VALUES (?, ?, ?) ON CONFLICT(code) DO UPDATE SET display_name_ko = excluded.display_name_ko`)
        .bind(cropCode, cropName, now).run();
      if (cultivarCode) {
        await env.DB.prepare(`INSERT INTO cultivars(
          code, display_name_ko, operational_status, supports_quality,
          supports_ripeness, supports_mite_warning, created_at
        ) VALUES (?, ?, 'DATA_COLLECTION', 0, 0, 0, ?)
        ON CONFLICT(code) DO UPDATE SET display_name_ko = excluded.display_name_ko`)
          .bind(cultivarCode, cultivarName || cultivarCode, now).run();
      }
      const existingItem = await env.DB.prepare(`SELECT id FROM farm_items
        WHERE farm_id = ? AND crop_code = ? AND IFNULL(cultivar_code, '') = IFNULL(?, '')`)
        .bind(farmId, cropCode, cultivarCode).first<{ id: string }>();
      const itemDisplayName = text(itemInput.displayName, '표시명') || [cultivarName, cropName].filter(Boolean).join(' ');
      if (existingItem) {
        await env.DB.prepare(`UPDATE farm_items SET display_name = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?`)
          .bind(itemDisplayName, now, existingItem.id).run();
      } else {
        await env.DB.prepare(`INSERT INTO farm_items(
          id, farm_id, crop_code, cultivar_code, display_name, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?)`)
          .bind(crypto.randomUUID(), farmId, cropCode, cultivarCode, itemDisplayName, now, now).run();
      }
      if (existingItem) updated += 1;
      else created += 1;
    }

    for (const memberInput of items(payload.members)) {
      const loginIdInput = text(memberInput.loginId, '로그인 ID', true, 160).toLowerCase();
      const loginId = loginIdInput.startsWith(`${farmId}:`) ? loginIdInput : `${farmId}:${loginIdInput}`;
      const provider = text(memberInput.identityProvider, '인증 제공자') || 'SITES';
      const subjectInput = text(memberInput.identitySubject, '인증 사용자 ID', false, 200);
      const subject = subjectInput
        ? subjectInput.startsWith(`${farmId}:`) ? subjectInput : `${farmId}:${subjectInput}`
        : null;
      const email = text(memberInput.email, '이메일', false, 200).toLowerCase() || null;
      const existingMember = await env.DB.prepare(`SELECT id FROM farm_members
        WHERE farm_id = ? AND (login_id = ? OR login_id = ?
          OR (? IS NOT NULL AND email IS NOT NULL AND lower(email) = ?)) LIMIT 1`)
        .bind(farmId, loginId, loginIdInput, email, email).first<{ id: string }>();
      const memberRole = (text(memberInput.role, '역할') || 'WORKER').toUpperCase();
      if (!['ADMIN', 'OWNER', 'WORKER'].includes(memberRole)) throw new Error('사용자 역할은 관리자, 사업주, 작업자 중 하나여야 합니다.');
      if (existingMember) {
        await env.DB.prepare(`UPDATE farm_members SET login_id = ?, identity_provider = ?,
          identity_subject = ?, email = ?, role = ?, status = 'ACTIVE',
          approved_at = COALESCE(approved_at, ?), joined_at = COALESCE(joined_at, ?), updated_at = ?
          WHERE id = ? AND farm_id = ?`)
          .bind(loginId, provider, subject, email, memberRole, now, now, now, existingMember.id, farmId).run();
      } else {
        await env.DB.prepare(`INSERT INTO farm_members(
          id, farm_id, login_id, identity_provider, identity_subject, email,
          approved_at, joined_at, role, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)`)
          .bind(crypto.randomUUID(), farmId, loginId, provider, subject, email,
            now, now, memberRole, now, now).run();
      }
      if (existingMember) updated += 1;
      else created += 1;
    }

    const houseIds = new Map<string, string>();
    const bedIds = new Map<string, string>();
    const zoneIds = new Map<string, string>();
    const houseInputs = items(payload.houses);
    for (const [houseIndex, houseInput] of houseInputs.entries()) {
      const houseCode = code(houseInput.code, '하우스');
      const existingHouse = await env.DB.prepare('SELECT id FROM houses WHERE farm_id = ? AND code = ?')
        .bind(farmId, houseCode).first<{ id: string }>();
      const houseId = existingHouse?.id ?? crypto.randomUUID();
      houseIds.set(houseCode, houseId);
      await env.DB.prepare(`INSERT INTO houses(
        id, farm_id, code, name, display_order, status, metadata_json, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
      ON CONFLICT(farm_id, code) DO UPDATE SET name = excluded.name, display_order = excluded.display_order,
        status = 'ACTIVE', metadata_json = excluded.metadata_json, updated_at = excluded.updated_at`)
        .bind(houseId, farmId, houseCode, text(houseInput.name, '하우스명', true),
          order(houseInput.displayOrder, houseIndex), metadata(houseInput.metadata), now, now).run();
      if (existingHouse) updated += 1;
      else created += 1;

      for (const [bedIndex, bedInput] of items(houseInput.beds).entries()) {
        const bedCode = code(bedInput.code, '베드');
        const existingBed = await env.DB.prepare('SELECT id FROM beds WHERE house_id = ? AND code = ?')
          .bind(houseId, bedCode).first<{ id: string }>();
        const bedId = existingBed?.id ?? crypto.randomUUID();
        bedIds.set(`${houseCode}/${bedCode}`, bedId);
        await env.DB.prepare(`INSERT INTO beds(
          id, house_id, code, name, display_order, status, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
        ON CONFLICT(house_id, code) DO UPDATE SET name = excluded.name, display_order = excluded.display_order,
          status = 'ACTIVE', metadata_json = excluded.metadata_json, updated_at = excluded.updated_at`)
          .bind(bedId, houseId, bedCode, text(bedInput.name, '베드명', true),
            order(bedInput.displayOrder, bedIndex), metadata(bedInput.metadata), now, now).run();
        if (existingBed) updated += 1;
        else created += 1;

        for (const [zoneIndex, zoneInput] of items(bedInput.zones).entries()) {
          const zoneCode = code(zoneInput.code, '구역');
          const existingZone = await env.DB.prepare('SELECT id FROM zones WHERE bed_id = ? AND code = ?')
            .bind(bedId, zoneCode).first<{ id: string }>();
          const zoneId = existingZone?.id ?? crypto.randomUUID();
          zoneIds.set(`${houseCode}/${bedCode}/${zoneCode}`, zoneId);
          await env.DB.prepare(`INSERT INTO zones(
            id, bed_id, code, name, display_order, status, metadata_json, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
          ON CONFLICT(bed_id, code) DO UPDATE SET name = excluded.name, display_order = excluded.display_order,
            status = 'ACTIVE', metadata_json = excluded.metadata_json, updated_at = excluded.updated_at`)
            .bind(zoneId, bedId, zoneCode, text(zoneInput.name, '구역명', true),
              order(zoneInput.displayOrder, zoneIndex), metadata(zoneInput.metadata), now, now).run();
          if (existingZone) updated += 1;
          else created += 1;
        }
      }
    }

    for (const cameraInput of items(payload.cameras)) {
      const cameraCode = code(cameraInput.code, '카메라');
      const houseCode = text(cameraInput.houseCode, '하우스 코드').toUpperCase();
      const bedCode = text(cameraInput.bedCode, '베드 코드').toUpperCase();
      const zoneCode = text(cameraInput.zoneCode, '구역 코드').toUpperCase();
      const houseId = houseCode ? houseIds.get(houseCode) ?? null : null;
      const bedId = houseCode && bedCode ? bedIds.get(`${houseCode}/${bedCode}`) ?? null : null;
      const zoneId = houseCode && bedCode && zoneCode ? zoneIds.get(`${houseCode}/${bedCode}/${zoneCode}`) ?? null : null;
      const existingCamera = await env.DB.prepare('SELECT id FROM cameras WHERE farm_id = ? AND code = ?')
        .bind(farmId, cameraCode).first<{ id: string }>();
      const cameraId = existingCamera?.id ?? crypto.randomUUID();
      await env.DB.prepare(`INSERT INTO cameras(
        id, farm_id, house_id, bed_id, zone_id, code, name, camera_type,
        source_type, external_ref, stream_url, connection_status, last_seen_at,
        status, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCONNECTED', NULL, 'ACTIVE', ?, ?)
      ON CONFLICT(farm_id, code) DO UPDATE SET house_id = excluded.house_id, bed_id = excluded.bed_id,
        zone_id = excluded.zone_id, name = excluded.name, camera_type = excluded.camera_type,
        source_type = excluded.source_type, external_ref = excluded.external_ref, stream_url = excluded.stream_url,
        status = 'ACTIVE', updated_at = excluded.updated_at`)
        .bind(cameraId, farmId, houseId, bedId, zoneId, cameraCode,
          text(cameraInput.name, '카메라명', true), text(cameraInput.cameraType, '카메라 종류', true),
          text(cameraInput.sourceType, '연결 방식', true), text(cameraInput.externalRef, '외부 참조', false, 240) || null,
          text(cameraInput.streamUrl, '실시간 영상 주소', false, 500) || null,
          now, now).run();
      if (existingCamera) updated += 1;
      else created += 1;
    }

    const existingSource = spreadsheetId
      ? await env.DB.prepare(`SELECT id FROM config_sources
          WHERE farm_id = ? AND source_type = ? AND spreadsheet_id = ?
            AND IFNULL(sheet_gid, '') = IFNULL(?, '')`)
          .bind(farmId, sourceType, spreadsheetId, sheetGid).first<{ id: string }>()
      : null;
    const sourceId = existingSource?.id ?? crypto.randomUUID();
    await env.DB.prepare(`INSERT INTO config_sources(
      id, farm_id, source_type, spreadsheet_id, sheet_gid, access_mode,
      mapping_json, status, last_imported_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, 'READ_ONLY', ?, 'ACTIVE', ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET farm_id = excluded.farm_id, mapping_json = excluded.mapping_json,
      access_mode = 'READ_ONLY', status = 'ACTIVE', last_imported_at = excluded.last_imported_at,
      updated_at = excluded.updated_at`)
      .bind(sourceId, farmId, sourceType, spreadsheetId, sheetGid,
        metadata(source.mapping), now, now, now).run();

    const rowsRead = 1 + cultivarInputs.length + houseInputs.length + [...bedIds].length + [...zoneIds].length + items(payload.cameras).length;
    const runId = crypto.randomUUID();
    await env.DB.prepare(`INSERT INTO config_import_runs(
      id, source_id, status, rows_read, rows_created, rows_updated,
      rows_rejected, checksum, error_summary, started_at, finished_at
    ) VALUES (?, ?, 'SUCCEEDED', ?, ?, ?, 0, ?, NULL, ?, ?)`)
      .bind(runId, sourceId, rowsRead, created, updated, text(source.checksum, '체크섬', false, 160) || null, now, now).run();

    return NextResponse.json({
      farmId,
      importRunId: runId,
      accessMode: 'READ_ONLY',
      rowsRead,
      rowsCreated: created,
      rowsUpdated: updated,
      message: '원본 시트에는 쓰지 않고 서비스 DB에만 반영했습니다.',
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '농가 설정 가져오기에 실패했습니다.' }, { status: 400 });
  }
}
