import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { recordScoutingFieldCheck } from '@/app/features/pests/application/scouting-service';
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
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const locationStateId = text(body.locationStateId, 100);
    const evidenceCode = text(body.evidenceCode, 80);
    const observationId = text(body.observationId, 100) || null;
    const note = text(body.note, 300) || null;
    if (!farmId || !locationStateId || !evidenceCode) {
      return NextResponse.json({ error: '예찰 구역과 현장 점검 결과를 선택해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.reviewAlerts || !member.id) {
      return NextResponse.json({ error: '현장 점검 결과를 남길 권한이 없습니다.' }, { status: 403 });
    }
    const checkedAt = text(body.checkedAt, 40) || new Date().toISOString();
    const result = await recordScoutingFieldCheck(new ScoutingRepository(env.DB), {
      farmId, locationStateId, memberId: member.id, evidenceCode, checkedAt,
      observationId, note, secondaryEvidence: body.secondaryEvidence,
    });
    return NextResponse.json({ ...result, message: '현장 관찰 사실을 기록했습니다.' }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '현장 점검 기록을 저장하지 못했습니다.' }, { status: 400 });
  }
}
