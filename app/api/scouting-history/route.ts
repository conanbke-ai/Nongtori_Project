import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { ScoutingRepository } from '@/app/features/pests/infrastructure/scouting-repository';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

export async function GET(request: Request) {
  try {
    await ensureSchema();
    const url = new URL(request.url);
    const farmId = url.searchParams.get('farmId')?.trim() ?? '';
    const locationStateId = url.searchParams.get('locationStateId')?.trim() ?? '';
    const requestedLimit = Number(url.searchParams.get('limit') ?? '50');
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(100, Math.floor(requestedLimit))) : 50;
    if (!farmId || !locationStateId) {
      return NextResponse.json({ error: '예찰 구역을 선택해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.viewHistory) {
      return NextResponse.json({ error: '이 농장의 예찰 이력을 볼 권한이 없습니다.' }, { status: 403 });
    }
    const history = await new ScoutingRepository(env.DB).locationHistory(farmId, locationStateId, limit);
    if (!history) return NextResponse.json({ error: '이 농장의 예찰 구역을 찾을 수 없습니다.' }, { status: 404 });
    return NextResponse.json(history);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '예찰 이력을 불러오지 못했습니다.' }, { status: 400 });
  }
}
