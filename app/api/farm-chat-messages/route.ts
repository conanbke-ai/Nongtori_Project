import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import {
  getFarmMember,
  publicMemberAccountCode,
  publicMemberName,
  publicSnapshotName,
  type FarmMember,
} from '@/app/lib/farm-auth';
import { detectSupportedLanguage } from '@/app/lib/detect-language';

export const runtime = 'edge';

type ChatMessageRow = {
  id: string;
  farm_id: string;
  author_member_id: string | null;
  author_name_snapshot: string;
  author_role_snapshot: string;
  author_account_snapshot: string;
  language: string;
  content: string;
  status: string;
  created_at: string;
  updated_at: string;
};

function textValue(value: unknown) {
  return typeof value === 'string' ? value.trim() : '';
}

function responseRow(row: ChatMessageRow, member: FarmMember) {
  const isMine = Boolean(member.id && row.author_member_id === member.id);
  const accountCode = publicMemberAccountCode({
    id: row.author_member_id,
    farmId: row.farm_id,
    role: row.author_role_snapshot,
  });
  return {
    id: row.id,
    author_name_snapshot: publicSnapshotName(row.author_name_snapshot, {
      accountCode,
      memberId: row.author_member_id,
      farmId: row.farm_id,
      role: row.author_role_snapshot,
    }),
    author_role_snapshot: row.author_role_snapshot,
    author_account_snapshot: accountCode,
    language: row.language,
    content: row.content,
    status: row.status,
    created_at: row.created_at,
    updated_at: row.updated_at,
    is_mine: isMine,
    can_delete: member.permissions.manageMembers || isMine,
  };
}

async function memberFor(request: Request, farmId: string) {
  if (!farmId || Array.from(farmId).length > 100) return null;
  return getFarmMember(request, farmId);
}

export async function GET(request: Request) {
  try {
    await ensureSchema();
    const farmId = textValue(new URL(request.url).searchParams.get('farmId'));
    const member = await memberFor(request, farmId);
    if (!member) {
      return NextResponse.json({ error: '이 농장의 대화를 볼 권한이 없습니다.' }, { status: 403 });
    }

    const rows = await env.DB.prepare(`SELECT * FROM (
        SELECT id, farm_id, author_member_id, author_name_snapshot, author_role_snapshot,
          author_account_snapshot, language, content, status, created_at, updated_at
        FROM farm_chat_messages
        WHERE farm_id = ? AND status = 'ACTIVE'
        ORDER BY created_at DESC, id DESC
        LIMIT 50
      ) recent
      ORDER BY created_at ASC, id ASC`)
      .bind(farmId).all<ChatMessageRow>();

    return NextResponse.json({
      rows: rows.results.map((row) => responseRow(row, member)),
      limit: 50,
    });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : '대화를 불러오지 못했습니다.',
    }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = textValue(body.farmId);
    const content = textValue(body.content);
    if (!farmId || Array.from(farmId).length > 100 || !content || Array.from(content).length > 500) {
      return NextResponse.json({ error: '대화 내용은 500자 이내로 입력해 주세요.' }, { status: 422 });
    }

    const member = await memberFor(request, farmId);
    if (!member || (!member.permissions.reviewAlerts && !member.id)) {
      return NextResponse.json({ error: '이 농장의 대화에 참여할 권한이 없습니다.' }, { status: 403 });
    }

    const detected = detectSupportedLanguage(
      content,
      body.languageHint ?? body.language,
      member.preferredLanguage,
    );
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const row: ChatMessageRow = {
      id,
      farm_id: farmId,
      author_member_id: member.id,
      author_name_snapshot: publicMemberName(member),
      author_role_snapshot: member.role,
      author_account_snapshot: publicMemberAccountCode(member),
      language: detected.language,
      content,
      status: 'ACTIVE',
      created_at: now,
      updated_at: now,
    };

    await env.DB.prepare(`INSERT INTO farm_chat_messages(
        id, farm_id, author_member_id, author_name_snapshot, author_role_snapshot,
        author_account_snapshot, language, content, status, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)`)
      .bind(id, farmId, member.id, row.author_name_snapshot, member.role,
        row.author_account_snapshot, detected.language, content, now, now).run();

    return NextResponse.json({
      row: responseRow(row, member),
      message: '대화를 보냈습니다.',
    }, { status: 201 });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : '대화를 보내지 못했습니다.',
    }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  try {
    await ensureSchema();
    const url = new URL(request.url);
    const farmId = textValue(url.searchParams.get('farmId'));
    const messageId = textValue(url.searchParams.get('messageId'));
    if (!farmId || Array.from(farmId).length > 100 || !messageId || Array.from(messageId).length > 100) {
      return NextResponse.json({ error: '삭제할 대화를 확인해 주세요.' }, { status: 422 });
    }

    const member = await memberFor(request, farmId);
    if (!member) {
      return NextResponse.json({ error: '이 농장의 대화를 삭제할 권한이 없습니다.' }, { status: 403 });
    }

    const existing = await env.DB.prepare(`SELECT id, farm_id, author_member_id,
        author_name_snapshot, author_role_snapshot, author_account_snapshot,
        language, content, status, created_at, updated_at
      FROM farm_chat_messages
      WHERE id = ? AND farm_id = ? LIMIT 1`)
      .bind(messageId, farmId).first<ChatMessageRow>();
    if (!existing || existing.status !== 'ACTIVE') {
      return NextResponse.json({ error: '삭제할 대화를 찾지 못했습니다.' }, { status: 404 });
    }

    const isMine = Boolean(member.id && existing.author_member_id === member.id);
    if (!member.permissions.manageMembers && !isMine) {
      return NextResponse.json({ error: '본인이 작성한 대화만 삭제할 수 있습니다.' }, { status: 403 });
    }

    const updatedAt = new Date().toISOString();
    await env.DB.prepare(`UPDATE farm_chat_messages
      SET status = 'DELETED', updated_at = ?
      WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
      .bind(updatedAt, messageId, farmId).run();

    return NextResponse.json({
      id: messageId,
      status: 'DELETED',
      updated_at: updatedAt,
      message: '대화를 삭제했습니다.',
    });
  } catch (error) {
    return NextResponse.json({
      error: error instanceof Error ? error.message : '대화를 삭제하지 못했습니다.',
    }, { status: 400 });
  }
}
