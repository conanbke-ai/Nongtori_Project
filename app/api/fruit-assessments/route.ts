import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { hasFarmPermission } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const MAX_FILE_BYTES = 25 * 1024 * 1024;

export async function POST(request: Request) {
  let uploadedKey = '';
  let farmItemId: string | null = null;
  try {
    const form = await request.formData();
    const cultivarInput = String(form.get('cultivar') ?? '').trim();
    const cultivar = cultivarInput === '설향' ? 'SEOLHYANG' : cultivarInput.toUpperCase();
    const farmId = String(form.get('farmId') ?? '').trim();
    if (!farmId) {
      return NextResponse.json({ error: '사진을 저장할 농장을 선택해 주세요.' }, { status: 422 });
    }
    const image = form.get('image');
    if (!(image instanceof File) || image.size === 0) {
      return NextResponse.json({ error: '과실 사진을 선택해 주세요.' }, { status: 422 });
    }
    if (!image.type.startsWith('image/') || image.size > MAX_FILE_BYTES) {
      return NextResponse.json({ error: '25MB 이하의 이미지 파일만 사용할 수 있습니다.' }, { status: 422 });
    }

    await ensureSchema();
    if (!await hasFarmPermission(request, farmId, 'uploadMedia')) {
      return NextResponse.json({ error: '이 농장의 촬영 자료를 접수할 권한이 없습니다.' }, { status: 403 });
    }
    const cultivarRow = await env.DB.prepare(`
      SELECT code FROM cultivars
      WHERE code = ? AND operational_status = 'ACTIVE'
        AND supports_quality = 1 AND supports_ripeness = 1
    `).bind(cultivar).first();
    if (!cultivarRow) {
      return NextResponse.json({ error: '이 품종의 등급·후숙도 기능은 아직 검증 중입니다.' }, { status: 422 });
    }

    const farm = await env.DB.prepare("SELECT id FROM farms WHERE id = ? AND status = 'ACTIVE'").bind(farmId).first();
    if (!farm) return NextResponse.json({ error: '등록된 농장을 찾을 수 없습니다.' }, { status: 422 });
    const item = await env.DB.prepare(`SELECT id FROM farm_items
      WHERE farm_id = ? AND cultivar_code = ? AND status = 'ACTIVE' ORDER BY created_at LIMIT 1`)
      .bind(farmId, cultivar).first<{ id: string }>();
    if (!item) return NextResponse.json({ error: '이 농장에 선택한 품종이 등록되어 있지 않습니다.' }, { status: 422 });
    farmItemId = item.id;

    const id = crypto.randomUUID();
    const captureSessionId = crypto.randomUUID();
    const extension = image.name.toLowerCase().match(/\.([a-z0-9]{1,8})$/)?.[1] ?? 'jpg';
    uploadedKey = `direct/${farmId}/fruit/${cultivar}/${id}.${extension}`;
    await env.FILES.put(uploadedKey, image.stream(), {
      httpMetadata: { contentType: image.type },
      customMetadata: { assessmentId: id, cultivar, originalName: image.name },
    });

    const createdAt = new Date().toISOString();
    const statements = [];
    statements.push(env.DB.prepare(`INSERT INTO capture_sessions(
        id, farm_id, camera_id, item_id, house_id, bed_id, zone_id, capture_mode,
        source_type, processing_status, started_at, ended_at, created_at
      ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL, 'SINGLE_CAPTURE',
        'PERSONAL_CAPTURE', 'UPLOADED_AWAITING_MODEL', ?, NULL, ?)`)
      .bind(captureSessionId, farmId, farmItemId, createdAt, createdAt));
    statements.push(env.DB.prepare(`
      INSERT INTO fruit_assessments(
        id, farm_id, capture_session_id, cultivar, source_type, capture_at,
        object_key, original_name, grade_prediction,
        ripeness_prediction, confidence, decision_status,
        processing_status, created_at
      ) VALUES (?, ?, ?, ?, 'PERSONAL_CAPTURE', ?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
    `).bind(
      id, farmId, captureSessionId, cultivar, createdAt, uploadedKey, image.name,
      'MODEL_NOT_VALIDATED', 'UPLOADED_AWAITING_MODEL', createdAt,
    ));
    await env.DB.batch(statements);

    return NextResponse.json(
      {
        assessmentId: id,
        processingStatus: 'UPLOADED_AWAITING_MODEL',
        message: '사진을 접수했습니다. 판독 기준 확인이 끝나면 결과를 보여드립니다.',
      },
      { status: 201 },
    );
  } catch (error) {
    if (uploadedKey) await env.FILES.delete(uploadedKey).catch(() => undefined);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : '사진 저장에 실패했습니다.' },
      { status: 400 },
    );
  }
}
