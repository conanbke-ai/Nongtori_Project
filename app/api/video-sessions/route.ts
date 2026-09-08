import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { hasFarmPermission } from '@/app/lib/farm-auth';
import { getAccessibleFarms } from '@/app/api/_lib/farm-access';

export const runtime = 'edge';

const SOURCE_TYPES = new Set(['ROBOT', 'PERSONAL_CAPTURE', 'VIDEO_IMPORT']);
const MODALITIES = new Set(['RGB_VIDEO', 'THERMAL_VIDEO', 'DUAL_SENSOR_VIDEO']);

function limitedText(value: unknown, name: string, required = false) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (required && !text) throw new Error(`${name} 값이 필요합니다.`);
  if (text.length > 240) throw new Error(`${name} 값이 너무 깁니다.`);
  return text;
}

export async function GET(request: Request) {
  await ensureSchema();
  const farms = await getAccessibleFarms(request);
  if (farms.length === 0) return NextResponse.json({ sessions: [] });
  const placeholders = farms.map(() => '?').join(',');
  const sessions = await env.DB.prepare(`
    SELECT cs.id, cs.capture_mode, cs.source_type, cs.processing_status, cs.started_at, cs.ended_at,
      f.name AS farm_name, h.name AS house_name, b.name AS bed_name, z.name AS zone_name, c.name AS camera_name
    FROM capture_sessions cs
    JOIN farms f ON f.id = cs.farm_id
    LEFT JOIN houses h ON h.id = cs.house_id AND h.farm_id = cs.farm_id
    LEFT JOIN beds b ON b.id = cs.bed_id AND b.house_id = h.id
    LEFT JOIN zones z ON z.id = cs.zone_id AND z.bed_id = b.id
    LEFT JOIN cameras c ON c.id = cs.camera_id
    WHERE cs.farm_id IN (${placeholders})
    ORDER BY cs.started_at DESC LIMIT 50
  `).bind(...farms.map((farm) => farm.id)).all();
  return NextResponse.json({ sessions: sessions.results });
}

export async function POST(request: Request) {
  try {
    const body = await request.json() as Record<string, unknown>;
    const farmId = limitedText(body.farmId, '농가', true);
    const cameraId = limitedText(body.cameraId, '카메라');
    const sourceType = limitedText(body.sourceType, '수집 방식', true);
    if (!SOURCE_TYPES.has(sourceType)) throw new Error('지원하지 않는 수집 방식입니다.');
    if (sourceType === 'ROBOT' && !cameraId) throw new Error('로봇 세션에는 등록된 카메라가 필요합니다.');

    await ensureSchema();
    const farm = await env.DB.prepare("SELECT id FROM farms WHERE id = ? AND status = 'ACTIVE'").bind(farmId).first();
    if (!farm) return NextResponse.json({ error: '활성 농가를 찾을 수 없습니다.' }, { status: 404 });
    if (!await hasFarmPermission(request, farmId, 'uploadMedia')) return NextResponse.json({ error: '이 농장의 촬영 자료를 접수할 권한이 없습니다.' }, { status: 403 });

    const camera = cameraId
      ? await env.DB.prepare(`SELECT id, house_id, bed_id, zone_id FROM cameras
          WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`).bind(cameraId, farmId).first<{
            id: string; house_id: string | null; bed_id: string | null; zone_id: string | null;
          }>()
      : null;
    if (cameraId && !camera) return NextResponse.json({ error: '이 농가에 연결된 카메라가 아닙니다.' }, { status: 422 });

    const now = new Date().toISOString();
    const startedAtInput = limitedText(body.startedAt, '촬영 시각');
    const startedAt = startedAtInput ? new Date(startedAtInput).toISOString() : now;
    const sessionId = crypto.randomUUID();
    const captureMode = sourceType === 'PERSONAL_CAPTURE' ? 'SINGLE_CAPTURE' : 'VIDEO';
    const videos = Array.isArray(body.videos) ? body.videos : [];

    const statements = [env.DB.prepare(`INSERT INTO capture_sessions(
      id, farm_id, camera_id, house_id, bed_id, zone_id, capture_mode,
      source_type, processing_status, started_at, ended_at, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REGISTERED', ?, NULL, ?)`)
      .bind(sessionId, farmId, camera?.id ?? null, camera?.house_id ?? null, camera?.bed_id ?? null,
        camera?.zone_id ?? null, captureMode, sourceType, startedAt, now)];

    for (const item of videos) {
      const video = item as Record<string, unknown>;
      const modality = limitedText(video.modality, '영상 종류', true);
      if (!MODALITIES.has(modality)) throw new Error('지원하지 않는 영상 종류입니다.');
      statements.push(env.DB.prepare(`INSERT INTO video_assets(
        id, capture_session_id, camera_id, modality, object_key, original_name,
        source_uri, duration_ms, frame_rate, frame_count, processing_status, created_at
      ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, 'REGISTERED', ?)`)
        .bind(crypto.randomUUID(), sessionId, camera?.id ?? null, modality,
          limitedText(video.originalName, '파일명') || null, limitedText(video.sourceUri, '원본 경로') || null,
          Number.isFinite(Number(video.durationMs)) ? Number(video.durationMs) : null,
          Number.isFinite(Number(video.frameRate)) ? Number(video.frameRate) : null,
          Number.isInteger(Number(video.frameCount)) ? Number(video.frameCount) : null, now));
    }
    await env.DB.batch(statements);

    return NextResponse.json({
      sessionId,
      processingStatus: 'REGISTERED',
      message: '세션과 내부 식별값을 자동 생성했습니다. 사용자가 프레임 번호나 페어링 ID를 입력할 필요가 없습니다.',
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '영상 세션 생성에 실패했습니다.' }, { status: 400 });
  }
}
