import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { ensureScoutingRuntime } from '@/db/scouting-runtime';
import { correctScoutingFieldCheck } from '@/app/features/pests/application/scouting-service';
import { ScoutingRepository } from '@/app/features/pests/infrastructure/scouting-repository';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

function text(value: unknown, max = 300) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error(`입력값은 ${max}자 이내여야 합니다.`);
  return result;
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    await ensureScoutingRuntime();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const fieldCheckId = text(body.fieldCheckId, 100);
    const correctionKind = text(body.correctionKind, 20);
    const replacementEvidenceCode = text(body.replacementEvidenceCode, 80) || null;
    const reasonCode = text(body.reasonCode, 40) || 'MISCLICK';
    const note = text(body.note, 300) || null;
    if (!farmId || !fieldCheckId || !['REPLACE', 'VOID'].includes(correctionKind)) {
      return NextResponse.json({ error: '수정할 현장 점검 기록과 수정 유형을 확인해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.reviewAlerts || !member.id) {
      return NextResponse.json({ error: '현장 점검 기록을 수정할 권한이 없습니다.' }, { status: 403 });
    }
    const correctedAt = text(body.correctedAt, 40) || new Date().toISOString();
    const result = await correctScoutingFieldCheck(new ScoutingRepository(env.DB), {
      farmId,
      fieldCheckId,
      memberId: member.id,
      correctionKind: correctionKind as 'REPLACE' | 'VOID',
      replacementEvidenceCode,
      reasonCode: reasonCode as 'MISCLICK' | 'WRONG_OBSERVATION' | 'DUPLICATE' | 'OTHER',
      correctedAt,
      note,
    });
    return NextResponse.json({ ...result, message: '현장 점검 입력을 수정 기록으로 남겼습니다.' }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '현장 점검 입력을 수정하지 못했습니다.' }, { status: 400 });
  }
}
