import { env } from 'cloudflare:workers';
import { desc, eq } from 'drizzle-orm';
import { NextResponse } from 'next/server';
import { ensureSchema, getDb } from '@/db';
import { observations } from '@/db/schema';
import { hasFarmPermission } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const FILE_FIELDS = [
  ['rgb', 'RGB'],
  ['thermal', 'REAL_THERMAL'],
  ['macro', 'LEAF_BACKSIDE_RGB'],
] as const;

const CAPTURE_METHODS = new Set([
  'PAIRED_STILL',
  'EXTRACTED_VIDEO_FRAMES',
  'DUAL_SENSOR_SIMULTANEOUS',
]);

function textField(form: FormData, name: string, required = false) {
  const value = String(form.get(name) ?? '').trim();
  if (required && !value) throw new Error(`${name} is required`);
  if (value.length > 120) throw new Error(`${name} is too long`);
  return value;
}

function safeExtension(name: string) {
  const match = name.toLowerCase().match(/\.([a-z0-9]{1,8})$/);
  return match?.[1] ?? 'bin';
}

export async function GET(request: Request) {
  await ensureSchema();
  const farmId = new URL(request.url).searchParams.get('farmId')?.trim() ?? '';
  if (!farmId) return NextResponse.json({ error: '조회할 농장을 선택해 주세요.' }, { status: 400 });
  if (!await hasFarmPermission(request, farmId, 'viewHistory')) {
    return NextResponse.json({ error: '이 농장의 관측 기록을 볼 권한이 없습니다.' }, { status: 403 });
  }
  const rows = await getDb().select().from(observations)
    .where(eq(observations.farmId, farmId))
    .orderBy(desc(observations.captureAt)).limit(50);
  return NextResponse.json({ observations: rows });
}

export async function POST(request: Request) {
  const uploadedKeys: string[] = [];
  try {
    const form = await request.formData();
    const cultivarInput = textField(form, 'cultivar', true);
    const cultivar = cultivarInput === '설향' ? 'SEOLHYANG' : cultivarInput.toUpperCase();
    const farmId = textField(form, 'farmId', true);
    const houseId = textField(form, 'houseId', true);
    const bedId = textField(form, 'bedId', true);
    const zoneId = textField(form, 'zoneId', true);
    await ensureSchema();
    if (!await hasFarmPermission(request, farmId, 'uploadMedia')) {
      return NextResponse.json({ error: '이 농장의 관측 자료를 접수할 권한이 없습니다.' }, { status: 403 });
    }
    const cultivarRow = await env.DB.prepare(`SELECT c.code FROM cultivars c
      JOIN farm_items fi ON fi.cultivar_code = c.code
      WHERE c.code = ? AND c.operational_status = 'ACTIVE'
        AND fi.farm_id = ? AND fi.status = 'ACTIVE' LIMIT 1`)
      .bind(cultivar, farmId).first();
    if (!cultivarRow) {
      return NextResponse.json({ error: '아직 운영 검증이 끝나지 않은 품종입니다.' }, { status: 422 });
    }
    const location = await env.DB.prepare(`SELECT z.id FROM zones z
      JOIN beds b ON b.id = z.bed_id
      JOIN houses h ON h.id = b.house_id
      WHERE h.farm_id = ? AND h.id = ? AND b.id = ? AND z.id = ?
        AND h.status = 'ACTIVE' AND b.status = 'ACTIVE' AND z.status = 'ACTIVE' LIMIT 1`)
      .bind(farmId, houseId, bedId, zoneId).first();
    if (!location) {
      return NextResponse.json({ error: '선택한 하우스·베드·구역이 이 농장에 속하지 않습니다.' }, { status: 422 });
    }
    const plantId = textField(form, 'plantId');
    const leafId = textField(form, 'leafId');
    const captureMethod = textField(form, 'captureMethod', true);
    if (!CAPTURE_METHODS.has(captureMethod)) throw new Error('지원하지 않는 촬영 방식입니다.');
    const pairingId = textField(form, 'pairingId', true);
    const sourceVideoId = textField(form, 'sourceVideoId');
    const rgbFrameIndexInput = textField(form, 'rgbFrameIndex');
    const thermalFrameIndexInput = textField(form, 'thermalFrameIndex');
    const parseFrameIndex = (value: string, field: string) => {
      if (!value) return null;
      const parsed = Number(value);
      if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${field}는 0 이상의 정수여야 합니다.`);
      return parsed;
    };
    const rgbFrameIndex = parseFrameIndex(rgbFrameIndexInput, 'RGB 프레임 번호');
    const thermalFrameIndex = parseFrameIndex(thermalFrameIndexInput, '열화상 프레임 번호');
    if (captureMethod === 'EXTRACTED_VIDEO_FRAMES' && !sourceVideoId) {
      throw new Error('영상 프레임 자료에는 원본 영상 ID가 필요합니다.');
    }
    if (sourceVideoId) {
      const sourceVideo = await env.DB.prepare(`SELECT va.id FROM video_assets va
        JOIN capture_sessions cs ON cs.id = va.capture_session_id
        WHERE va.id = ? AND cs.farm_id = ? LIMIT 1`)
        .bind(sourceVideoId, farmId).first();
      if (!sourceVideo) {
        return NextResponse.json({ error: '이 농장에 등록된 원본 영상이 아닙니다.' }, { status: 422 });
      }
    }
    const captureAtInput = textField(form, 'captureAt');
    const captureAt = captureAtInput ? new Date(captureAtInput).toISOString() : new Date().toISOString();
    const createdAt = new Date().toISOString();
    const observationId = crypto.randomUUID();

    const files = FILE_FIELDS.flatMap(([field, modality]) => {
      const value = form.get(field);
      if (!(value instanceof File) || value.size === 0) return [];
      if (value.size > MAX_FILE_BYTES) throw new Error(`${field} file exceeds 50 MB`);
      return [{ field, modality, file: value, assetId: crypto.randomUUID() }];
    });
    if (!files.some((item) => item.field === 'rgb') || !files.some((item) => item.field === 'thermal')) {
      return NextResponse.json({ error: 'RGB와 radiometric 열화상 원본이 모두 필요합니다.' }, { status: 422 });
    }

    await Promise.all(
      files.map(async ({ modality, file, assetId }) => {
        const key = [farmId, houseId, bedId, zoneId, observationId, `${modality}-${assetId}.${safeExtension(file.name)}`].join('/');
        uploadedKeys.push(key);
        await env.FILES.put(key, file.stream(), {
          httpMetadata: { contentType: file.type || 'application/octet-stream' },
          customMetadata: { observationId, modality, originalName: file.name },
        });
      }),
    );

    await ensureSchema();
    const statements = [
      env.DB.prepare(`
        INSERT INTO observations(
          id, farm_id, house_id, bed_id, zone_id, plant_id, leaf_id,
          cultivar, pest_species, capture_at, visual_symptom_status,
          active_pest_status, decision_status, environment_status,
          processing_status, capture_method, pairing_id, source_video_id,
          rgb_frame_index, thermal_frame_index, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        observationId, farmId, houseId, bedId, zoneId, plantId || null, leafId || null,
        cultivar, 'Tetranychus urticae', captureAt, 'NOT_ASSESSED',
        'NOT_ASSESSED', 'INSUFFICIENT_EVIDENCE', 'NOT_ASSESSED', 'UPLOADED',
        captureMethod, pairingId, sourceVideoId || null, rgbFrameIndex, thermalFrameIndex, createdAt,
      ),
      ...files.map(({ modality, file, assetId }, index) =>
        env.DB.prepare(`
          INSERT INTO assets(
            id, observation_id, modality, object_key, original_name,
            content_type, size_bytes, created_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        `).bind(
          assetId, observationId, modality, uploadedKeys[index], file.name,
          file.type || 'application/octet-stream', file.size, createdAt,
        ),
      ),
    ];
    await env.DB.batch(statements);

    return NextResponse.json(
      { observationId, processingStatus: 'UPLOADED', assetCount: files.length },
      { status: 201 },
    );
  } catch (error) {
    await Promise.all(uploadedKeys.map((key) => env.FILES.delete(key).catch(() => undefined)));
    const message = error instanceof Error ? error.message : '관측 저장에 실패했습니다.';
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
