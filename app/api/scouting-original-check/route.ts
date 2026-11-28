import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { getFarmMember } from '@/app/lib/farm-auth';
import { readOriginalFieldCheck } from '@/app/features/pests/application/scouting-original-check';

export const runtime = 'edge';
const reply = (body: unknown, status: number) => NextResponse.json(body, {
  status, headers: { 'Cache-Control': 'no-store' },
});

export async function GET(request: Request) {
  try {
    const query = new URL(request.url).searchParams;
    const [farmId, locationId, checkId] = ['farmId', 'locationStateId', 'fieldCheckId']
      .map(key => query.get(key)?.trim() ?? '');
    if ([farmId, locationId, checkId].some(id => !id || id.length > 100)) {
      return reply({ error: 'INVALID_ORIGINAL_CHECK_SCOPE' }, 422);
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.viewHistory) return reply({ error: 'FORBIDDEN' }, 403);
    const original = await readOriginalFieldCheck(env.DB, farmId, locationId, checkId);
    if (!original) return reply({ error: 'ORIGINAL_CHECK_NOT_FOUND' }, 404);
    return reply({ original }, 200);
  } catch {
    return reply({ error: 'ORIGINAL_CHECK_UNAVAILABLE' }, 503);
  }
}
