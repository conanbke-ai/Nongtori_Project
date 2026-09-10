import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { hasFarmPermission } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const MAX_TOTAL_BYTES = 90 * 1024 * 1024;

function safeExtension(name: string) {
  return name.toLowerCase().match(/\.([a-z0-9]{1,8})$/)?.[1] ?? 'mp4';
}

export async function POST(request: Request) {
  const uploadedKeys: string[] = [];
  try {
    const form = await request.formData();
    const farmId = String(form.get('farmId') ?? '').trim();
    const itemId = String(form.get('itemId') ?? '').trim();
    const zoneId = String(form.get('zoneId') ?? '').trim();
    const rgb = form.get('rgbVideo');
    const thermal = form.get('thermalVideo');
    if (!farmId) return NextResponse.json({ error: '농장을 먼저 선택해 주세요.' }, { status: 422 });
    if (!zoneId) return NextResponse.json({ error: '영상을 촬영한 위치를 선택해 주세요.' }, { status: 422 });
    if (!(rgb instanceof File) || rgb.size === 0 || !rgb.type.startsWith('video/')) {
      return NextResponse.json({ error: '일반 영상 파일을 선택해 주세요.' }, { status: 422 });
    }
    const files = [
      { file: rgb, modality: 'RGB_VIDEO' },
      ...(thermal instanceof File && thermal.size > 0 ? [{ file: thermal, modality: 'THERMAL_VIDEO' }] : []),
    ];
    if (files.some(({ file }) => !file.type.startsWith('video/'))) {
      return NextResponse.json({ error: '영상 파일만 접수할 수 있습니다.' }, { status: 422 });
    }
    if (files.reduce((total, { file }) => total + file.size, 0) > MAX_TOTAL_BYTES) {
      return NextResponse.json({ error: '두 영상의 합계는 90MB 이하여야 합니다.' }, { status: 413 });
    }

    await ensureSchema();
    const farm = await env.DB.prepare("SELECT id FROM farms WHERE id = ? AND status = 'ACTIVE'").bind(farmId).first();
    if (!farm) return NextResponse.json({ error: '등록된 농장을 찾을 수 없습니다.' }, { status: 422 });
    if (!await hasFarmPermission(request, farmId, 'uploadMedia')) return NextResponse.json({ error: '이 농장의 촬영 자료를 접수할 권한이 없습니다.' }, { status: 403 });
    if (itemId) {
      const item = await env.DB.prepare("SELECT id FROM farm_items WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'")
        .bind(itemId, farmId).first();
      if (!item) return NextResponse.json({ error: '이 농장의 재배 품목이 아닙니다.' }, { status: 422 });
    }
    const location = await env.DB.prepare(`SELECT zone.id AS zone_id, bed.id AS bed_id, house.id AS house_id
      FROM zones zone JOIN beds bed ON bed.id = zone.bed_id
      JOIN houses house ON house.id = bed.house_id
      WHERE zone.id = ? AND house.farm_id = ?
        AND house.status != 'ARCHIVED' AND bed.status != 'ARCHIVED' AND zone.status != 'ARCHIVED'
      LIMIT 1`).bind(zoneId, farmId).first<{ zone_id: string; bed_id: string; house_id: string }>();
    if (!location) return NextResponse.json({ error: '이 농장에 등록된 촬영 위치가 아닙니다.' }, { status: 422 });

    const sessionId = crypto.randomUUID();
    const now = new Date().toISOString();
    const assets = files.map(({ file, modality }) => ({
      id: crypto.randomUUID(), file, modality,
      key: `video-import/${farmId}/${sessionId}/${modality}-${crypto.randomUUID()}.${safeExtension(file.name)}`,
    }));
    await Promise.all(assets.map(async (asset) => {
      uploadedKeys.push(asset.key);
      await env.FILES.put(asset.key, asset.file.stream(), {
        httpMetadata: { contentType: asset.file.type },
        customMetadata: { captureSessionId: sessionId, modality: asset.modality, analysisScope: 'FRUIT_AND_MITE', originalName: asset.file.name },
      });
    }));

    await env.DB.batch([
      env.DB.prepare(`INSERT INTO capture_sessions(
        id, farm_id, camera_id, item_id, house_id, bed_id, zone_id, capture_mode,
        source_type, processing_status, started_at, ended_at, created_at
      ) VALUES (?, ?, NULL, ?, ?, ?, ?, 'COMBINED_VIDEO', 'VIDEO_IMPORT',
        'UPLOADED_AWAITING_FRAME_EXTRACTION', ?, NULL, ?)`)
        .bind(sessionId, farmId, itemId || null, location.house_id, location.bed_id, location.zone_id, now, now),
      ...assets.map((asset) => env.DB.prepare(`INSERT INTO video_assets(
        id, capture_session_id, camera_id, modality, object_key, original_name,
        source_uri, duration_ms, frame_rate, frame_count, processing_status, created_at
      ) VALUES (?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, NULL,
        'UPLOADED_AWAITING_FRAME_EXTRACTION', ?)`)
        .bind(asset.id, sessionId, asset.modality, asset.key, asset.file.name, now)),
    ]);

    return NextResponse.json({
      sessionId,
      processingStatus: 'UPLOADED_AWAITING_FRAME_EXTRACTION',
      pairedModalities: assets.map((asset) => asset.modality),
      analysisScope: ['FRUIT_RIPENESS_GRADE', 'MITE_RGB_SCREENING', ...(assets.length === 2 ? ['MITE_THERMAL_PRIMARY'] : [])],
      message: assets.length === 2
        ? '일반 영상과 열화상을 한 촬영 건으로 묶어 접수했습니다. 영상을 장면별로 나눌 예정입니다.'
        : '일반 영상을 접수했습니다. 과실과 잎을 살펴볼 수 있도록 장면별로 나눌 예정입니다.',
    }, { status: 201 });
  } catch (error) {
    await Promise.all(uploadedKeys.map((key) => env.FILES.delete(key).catch(() => undefined)));
    return NextResponse.json({ error: error instanceof Error ? error.message : '영상 접수에 실패했습니다.' }, { status: 400 });
  }
}
