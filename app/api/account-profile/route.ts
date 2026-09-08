import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const supportedLanguages = new Set(['ko', 'vi', 'th', 'zh-CN']);

function text(value: unknown, max: number) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error('입력한 내용을 조금 줄여 주세요.');
  return result;
}

export async function PATCH(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const updatesNickname = Object.prototype.hasOwnProperty.call(body, 'displayName');
    const displayName = text(body.displayName, 30);
    const preferredLanguage = text(body.preferredLanguage, 10) || 'ko';
    if (!farmId || !supportedLanguages.has(preferredLanguage)) {
      return NextResponse.json({ error: '사용할 언어를 확인해 주세요.' }, { status: 422 });
    }
    if (updatesNickname && !displayName) {
      return NextResponse.json({ error: '농장 기록에 표시할 별명을 입력해 주세요.' }, { status: 422 });
    }
    if (updatesNickname && displayName.includes('@')) {
      return NextResponse.json({ error: '이메일 대신 사용할 별명을 입력해 주세요.' }, { status: 422 });
    }
    const member = await getFarmMember(request, farmId);
    if (!member?.id) return NextResponse.json({ error: '수정할 계정 정보를 찾지 못했습니다.' }, { status: 404 });
    await env.DB.prepare(`UPDATE farm_members SET display_name = ?, preferred_language = ?, updated_at = ?
      WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
      .bind(updatesNickname ? displayName : member.displayName, preferredLanguage,
        new Date().toISOString(), member.id, farmId).run();
    return NextResponse.json({ message: updatesNickname ? '별명을 저장했습니다.' : '사용 언어를 저장했습니다.' });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '내 정보를 저장하지 못했습니다.' }, { status: 400 });
  }
}
