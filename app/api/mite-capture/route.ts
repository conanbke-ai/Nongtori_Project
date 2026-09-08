import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { hasFarmPermission } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const MAX_TOTAL_BYTES = 40 * 1024 * 1024;

function extension(name: string) {
  return name.toLowerCase().match(/\.([a-z0-9]{1,8})$/)?.[1] ?? 'jpg';
}

export async function POST(request: Request) {
  const uploadedKeys: string[] = [];
  try {
    const form = await request.formData();
    const farmId = String(form.get('farmId') ?? '').trim();
    const itemId = String(form.get('itemId') ?? '').trim();
    const rgb = form.get('rgbImage');
    const thermal = form.get('thermalImage');
    if (!farmId) return NextResponse.json({ error: '농장을 먼저 선택해 주세요.' }, { status: 422 });
    if (!(rgb instanceof File) || rgb.size === 0 || !rgb.type.startsWith('image/')) {
      return NextResponse.json({ error: '잎의 일반 사진을 선택해 주세요.' }, { status: 422 });
    }
    const files = [
      { file: rgb, modality: 'LEAF_RGB' },
      ...(thermal instanceof File && thermal.size > 0 ? [{ file: thermal, modality: 'LEAF_THERMAL' }] : []),
    ];
    if (files.some(({ file }) => !file.type.startsWith('image/'))) {
      return NextResponse.json({ error: '이미지 파일만 접수할 수 있습니다.' }, { status: 422 });
    }
    if (files.reduce((sum, { file }) => sum + file.size, 0) > MAX_TOTAL_BYTES) {
      return NextResponse.json({ error: '사진 합계는 40MB 이하여야 합니다.' }, { status: 413 });
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

    const sessionId = crypto.randomUUID();
    const now = new Date().toISOString();
    const assets = files.map(({ file, modality }) => ({
      id: crypto.randomUUID(), file, modality,
      key: `direct/${farmId}/mite/${sessionId}/${modality}-${crypto.randomUUID()}.${extension(file.name)}`,
    }));
    await Promise.all(assets.map(async (asset) => {
      uploadedKeys.push(asset.key);
      await env.FILES.put(asset.key, asset.file.stream(), {
        httpMetadata: { contentType: asset.file.type },
        customMetadata: { captureSessionId: sessionId, modality: asset.modality, originalName: asset.file.name },
      });
    }));

    await env.DB.batch([
      env.DB.prepare(`INSERT INTO capture_sessions(
        id, farm_id, camera_id, item_id, house_id, bed_id, zone_id, capture_mode,
        source_type, processing_status, started_at, ended_at, created_at
      ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL, 'SINGLE_CAPTURE',
        'PERSONAL_CAPTURE', 'UPLOADED_AWAITING_MODEL', ?, NULL, ?)`)
        .bind(sessionId, farmId, itemId || null, now, now),
      ...assets.map((asset) => env.DB.prepare(`INSERT INTO capture_assets(
        id, capture_session_id, modality, object_key, original_name, content_type, size_bytes, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(asset.id, sessionId, asset.modality, asset.key, asset.file.name, asset.file.type, asset.file.size, now)),
    ]);

    return NextResponse.json({
      sessionId,
      processingStatus: 'UPLOADED_AWAITING_MODEL',
      message: assets.length === 2
        ? '잎의 일반 사진과 열화상 사진을 한 묶음으로 접수했습니다.'
        : '잎의 일반 사진을 접수했습니다. 같은 잎의 열화상이 있으면 온도 차이도 함께 확인할 수 있습니다.',
    }, { status: 201 });
  } catch (error) {
    await Promise.all(uploadedKeys.map((key) => env.FILES.delete(key).catch(() => undefined)));
    return NextResponse.json({ error: error instanceof Error ? error.message : '사진 접수에 실패했습니다.' }, { status: 400 });
  }
}
