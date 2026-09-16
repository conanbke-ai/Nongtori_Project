import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { ensureScoutingRuntime } from '@/db/scouting-runtime';
import { resolveScoutingCase } from '@/app/features/pests/application/scouting-service';
import { ScoutingRepository } from '@/app/features/pests/infrastructure/scouting-repository';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

function text(value: unknown, max = 200) {
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
    const locationStateId = text(body.locationStateId, 100);
    const reasonCode = text(body.reasonCode, 60);
    if (!farmId || !locationStateId || !reasonCode) {
      return NextResponse.json({ error: '예찰 구역과 종료 사유를 선택해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.reviewAlerts || !member.id) {
      return NextResponse.json({ error: '예찰 건을 종료할 권한이 없습니다.' }, { status: 403 });
    }
    const resolvedAt = text(body.resolvedAt, 40) || new Date().toISOString();
    const result = await resolveScoutingCase(new ScoutingRepository(env.DB), {
      farmId,
      locationStateId,
      memberId: member.id,
      reasonCode,
      resolvedAt,
    });
    return NextResponse.json({ ...result, message: '예찰 건을 종료했습니다.' }, { status: 200 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '예찰 건을 종료하지 못했습니다.' }, { status: 400 });
  }
}
