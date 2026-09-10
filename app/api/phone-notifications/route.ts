import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

type SmsBindings = typeof env & {
  SMS_VERIFICATION_URL?: string;
  SMS_VERIFICATION_TOKEN?: string;
  PHONE_VERIFICATION_PEPPER?: string;
};

function normalizePhone(value: unknown) {
  return typeof value === 'string' ? value.replace(/[^0-9]/g, '') : '';
}

function text(value: unknown, max: number) {
  const result = typeof value === 'string' ? value.trim() : '';
  return result.slice(0, max);
}

async function hashCode(challengeId: string, code: string, pepper: string) {
  const bytes = new TextEncoder().encode(`${challengeId}:${code}:${pepper}`);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function makeCode() {
  const value = new Uint32Array(1);
  crypto.getRandomValues(value);
  return String(100000 + (value[0] % 900000));
}

export async function GET(request: Request) {
  await ensureSchema();
  const farmId = new URL(request.url).searchParams.get('farmId')?.trim() ?? '';
  const member = await getFarmMember(request, farmId);
  if (!member) return NextResponse.json({ error: '계정 정보를 확인할 수 없습니다.' }, { status: 403 });
  const bindings = env as SmsBindings;
  return NextResponse.json({ deliveryAvailable: Boolean(
    bindings.SMS_VERIFICATION_URL && bindings.SMS_VERIFICATION_TOKEN && bindings.PHONE_VERIFICATION_PEPPER,
  ) });
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = text(body.farmId, 100);
    const action = text(body.action, 30);
    const member = await getFarmMember(request, farmId);
    if (!member?.id) return NextResponse.json({ error: '계정 정보를 확인할 수 없습니다.' }, { status: 403 });

    if (action === 'toggle') {
      const enabled = body.enabled === true;
      const current = await env.DB.prepare(`SELECT phone_verified_at FROM farm_members WHERE id = ? AND farm_id = ?`)
        .bind(member.id, farmId).first<{ phone_verified_at: string | null }>();
      if (enabled && !current?.phone_verified_at) {
        return NextResponse.json({ error: '휴대폰 인증을 먼저 완료해 주세요.' }, { status: 422 });
      }
      await env.DB.prepare(`UPDATE farm_members SET notifications_enabled = ?, updated_at = ? WHERE id = ?`)
        .bind(enabled ? 1 : 0, new Date().toISOString(), member.id).run();
      return NextResponse.json({ message: enabled ? '응애 알림을 받도록 설정했습니다.' : '문자 알림을 껐습니다.' });
    }

    const bindings = env as SmsBindings;
    const pepper = bindings.PHONE_VERIFICATION_PEPPER;
    if (action === 'request') {
      const phone = normalizePhone(body.phone);
      if (!/^01[016789]\d{7,8}$/.test(phone)) {
        return NextResponse.json({ error: '휴대폰 번호를 다시 확인해 주세요.' }, { status: 422 });
      }
      if (!bindings.SMS_VERIFICATION_URL || !bindings.SMS_VERIFICATION_TOKEN || !pepper) {
        return NextResponse.json({ error: '문자 인증 서비스 연결 전입니다. 업체 관리자에게 문의해 주세요.' }, { status: 503 });
      }
      const alreadyUsed = await env.DB.prepare(`SELECT id FROM farm_members
        WHERE farm_id = ? AND phone = ? AND phone_verified_at IS NOT NULL AND id != ? AND status = 'ACTIVE' LIMIT 1`)
        .bind(farmId, phone, member.id).first();
      if (alreadyUsed) return NextResponse.json({ error: '이미 다른 계정에서 인증한 번호입니다.' }, { status: 409 });
      const recent = await env.DB.prepare(`SELECT created_at FROM phone_verification_challenges
        WHERE member_id = ? ORDER BY created_at DESC LIMIT 1`).bind(member.id).first<{ created_at: string }>();
      if (recent && Date.now() - new Date(recent.created_at).getTime() < 60_000) {
        return NextResponse.json({ error: '인증번호는 1분 뒤 다시 요청할 수 있습니다.' }, { status: 429 });
      }
      const challengeId = crypto.randomUUID();
      const code = makeCode();
      const now = new Date();
      const expiresAt = new Date(now.getTime() + 5 * 60_000).toISOString();
      const codeHash = await hashCode(challengeId, code, pepper);
      const delivery = await fetch(bindings.SMS_VERIFICATION_URL, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${bindings.SMS_VERIFICATION_TOKEN}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify({
          to: phone,
          type: 'PHONE_VERIFICATION',
          code,
          expiresInMinutes: 5,
          message: `[농토리 운영센터] 인증번호는 ${code}입니다. 5분 안에 입력해 주세요.`,
        }),
      });
      if (!delivery.ok) return NextResponse.json({ error: '인증 문자를 보내지 못했습니다. 잠시 후 다시 시도해 주세요.' }, { status: 502 });
      await env.DB.prepare(`INSERT INTO phone_verification_challenges(
        id, farm_id, member_id, phone, code_hash, expires_at, attempts, consumed_at, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?)`)
        .bind(challengeId, farmId, member.id, phone, codeHash, expiresAt, now.toISOString()).run();
      return NextResponse.json({ challengeId, expiresAt, message: '인증번호를 보냈습니다.' }, { status: 201 });
    }

    if (action === 'confirm') {
      if (!pepper) return NextResponse.json({ error: '문자 인증 서비스 연결 전입니다.' }, { status: 503 });
      const challengeId = text(body.challengeId, 100);
      const code = text(body.code, 10);
      const challenge = await env.DB.prepare(`SELECT id, phone, code_hash, expires_at, attempts, consumed_at
        FROM phone_verification_challenges WHERE id = ? AND farm_id = ? AND member_id = ? LIMIT 1`)
        .bind(challengeId, farmId, member.id).first<{
          id: string;
          phone: string;
          code_hash: string;
          expires_at: string;
          attempts: number;
          consumed_at: string | null;
        }>();
      if (!challenge || challenge.consumed_at || challenge.attempts >= 5 || new Date(challenge.expires_at).getTime() < Date.now()) {
        return NextResponse.json({ error: '인증 시간이 지났습니다. 인증번호를 다시 받아 주세요.' }, { status: 410 });
      }
      const candidate = await hashCode(challengeId, code, pepper);
      if (candidate !== challenge.code_hash) {
        await env.DB.prepare(`UPDATE phone_verification_challenges SET attempts = attempts + 1 WHERE id = ?`)
          .bind(challengeId).run();
        return NextResponse.json({ error: '인증번호가 맞지 않습니다.' }, { status: 422 });
      }
      const alreadyUsed = await env.DB.prepare(`SELECT id FROM farm_members
        WHERE farm_id = ? AND phone = ? AND phone_verified_at IS NOT NULL
          AND status = 'ACTIVE' AND id != ? LIMIT 1`)
        .bind(farmId, challenge.phone, member.id).first();
      if (alreadyUsed) {
        return NextResponse.json({ error: '이미 다른 계정에서 인증한 번호입니다.' }, { status: 409 });
      }
      const now = new Date().toISOString();
      await env.DB.batch([
        env.DB.prepare(`UPDATE phone_verification_challenges SET consumed_at = ? WHERE id = ?`).bind(now, challengeId),
        env.DB.prepare(`UPDATE farm_members SET phone = ?, phone_verified_at = ?, notifications_enabled = 1,
          updated_at = ? WHERE id = ? AND farm_id = ?`).bind(challenge.phone, now, now, member.id, farmId),
      ]);
      return NextResponse.json({ message: '휴대폰 인증을 마쳤고 응애 알림을 켰습니다.' });
    }

    return NextResponse.json({ error: '요청 내용을 확인해 주세요.' }, { status: 400 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '휴대폰 인증을 처리하지 못했습니다.' }, { status: 400 });
  }
}
