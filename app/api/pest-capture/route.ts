import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { recordPestCapture, type PestCapturePhoto } from '@/app/features/pests/application/pest-capture-service';
import { findPestTarget } from '@/app/features/pests/domain/catalog';
import { MAX_CAPTURE_TOTAL_BYTES } from '@/app/features/pests/domain/capture-file-rules';
import { PestCaptureRepository } from '@/app/features/pests/infrastructure/pest-capture-repository';
import { R2PestCaptureStorage } from '@/app/features/pests/infrastructure/r2-pest-capture-storage';
import { hasFarmPermission } from '@/app/lib/farm-auth';

export const runtime = 'edge';

function readPestCapturePhotos(form: FormData): { photos: PestCapturePhoto[] } | { error: string; status: number } {
  const rgb = form.get('rgbImage');
  const thermal = form.get('thermalImage');
  if (!(rgb instanceof File) || rgb.size === 0 || !rgb.type.startsWith('image/')) {
    return { error: '잎의 일반 사진을 선택해 주세요.', status: 422 };
  }
  const photos: PestCapturePhoto[] = [{ file: rgb, modality: 'LEAF_RGB' }];
  if (thermal instanceof File && thermal.size > 0) {
    if (!thermal.type.startsWith('image/')) return { error: '이미지 파일만 접수할 수 있습니다.', status: 422 };
    photos.push({ file: thermal, modality: 'LEAF_THERMAL' });
  }
  if (photos.reduce((sum, { file }) => sum + file.size, 0) > MAX_CAPTURE_TOTAL_BYTES) {
    return { error: '사진 합계는 40MB 이하여야 합니다.', status: 413 };
  }
  return { photos };
}

const rejectedCapture = {
  FARM_NOT_FOUND: { status: 422, error: '등록된 농장을 찾을 수 없습니다.' },
  UPLOAD_FORBIDDEN: { status: 403, error: '이 농장의 촬영 자료를 접수할 권한이 없습니다.' },
  ITEM_NOT_FOUND: { status: 422, error: '이 농장의 재배 품목이 아닙니다.' },
};

export async function receivePestCapture(request: Request, legacyDefault?: string) {
  try {
    const form = await request.formData();
    const farmId = String(form.get('farmId') ?? '').trim();
    const itemId = String(form.get('itemId') ?? '').trim();
    const pestCode = String(form.get('pestCode') ?? legacyDefault ?? '').trim();
    if (!findPestTarget(pestCode)) return NextResponse.json({ error: '병해충 종류를 선택해 주세요.' }, { status: 422 });
    if (!farmId) return NextResponse.json({ error: '농장을 먼저 선택해 주세요.' }, { status: 422 });

    const input = readPestCapturePhotos(form);
    if ('error' in input) return NextResponse.json({ error: input.error }, { status: input.status });

    await ensureSchema();
    const result = await recordPestCapture({ farmId, itemId: itemId || null, pestCode, photos: input.photos }, {
      repository: new PestCaptureRepository(env.DB),
      storage: new R2PestCaptureStorage(env.FILES),
      canUpload: (requestedFarmId) => hasFarmPermission(request, requestedFarmId, 'uploadMedia'),
    });
    if (result.kind !== 'RECEIVED') {
      const { error, status } = rejectedCapture[result.kind];
      return NextResponse.json({ error }, { status });
    }
    return NextResponse.json({
      sessionId: result.sessionId,
      pestCode,
      processingStatus: 'UPLOADED_AWAITING_MODEL',
      message: result.photoCount === 2
        ? '잎의 일반 사진과 열화상 사진을 한 묶음으로 접수했습니다.'
        : '잎의 일반 사진을 접수했습니다. 같은 잎의 열화상이 있으면 온도 차이도 함께 확인할 수 있습니다.',
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '사진 접수에 실패했습니다.' }, { status: 400 });
  }
}

export async function POST(request: Request) { return receivePestCapture(request); }
