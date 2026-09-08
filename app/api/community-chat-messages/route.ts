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

const MAX_MESSAGES = 50;
const MAX_CONTENT_LENGTH = 300;
const RATE_LIMIT_COUNT = 6;
const RATE_LIMIT_WINDOW_MS = 60_000;

type CommunityChatMessageRow = {
  id: string;
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

function responseRow(row: CommunityChatMessageRow, member: FarmMember) {
  const isMine = row.author_member_id === member.id;
  const accountCode = publicMemberAccountCode({
    id: row.author_member_id,
    farmId: 'community',
    role: row.author_role_snapshot,
  });
  return {
    id: row.id,
    author_name_snapshot: publicSnapshotName(row.author_name_snapshot, {
      accountCode,
      memberId: row.author_member_id,
      farmId: 'community',
      role: row.author_role_snapshot,
    }),
    author_role_snapshot: row.author_role_snapshot,
    author_account_snapshot: accountCode,
    language: row.language,
    content: row.content,
    created_at: row.created_at,
    updated_at: row.updated_at,
    is_mine: isMine,
    can_delete: member.role === 'ADMIN' || isMine,
  };
}

async function approvedMemberFor(request: Request, farmId: string) {
  if (!farmId || Array.from(farmId).length > 100) return null;
  const member = await getFarmMember(request, farmId);
  if (!member?.id) return null;
  const approved = await env.DB.prepare(`SELECT id FROM farm_members
    WHERE id = ? AND farm_id = ? AND status = 'ACTIVE' AND approved_at IS NOT NULL
    LIMIT 1`).bind(member.id, farmId).first<{ id: string }>();
  return approved ? member : null;
}

function privateJson(body: Record<string, unknown>, init?: ResponseInit) {
  const headers = new Headers(init?.headers);
  headers.set('Cache-Control', 'private, no-store');
  return NextResponse.json(body, { ...init, headers });
}

export async function GET(request: Request) {
  try {
    await ensureSchema();
    const farmId = textValue(new URL(request.url).searchParams.get('farmId'));
    const member = await approvedMemberFor(request, farmId);
    if (!member) {
      return privateJson({ error: '승인된 농장 사용자만 이용자 라운지를 볼 수 있습니다.' }, { status: 403 });
    }

    const rows = await env.DB.prepare(`SELECT * FROM (
        SELECT id, author_member_id, author_name_snapshot, author_role_snapshot,
          author_account_snapshot, language, content, status, created_at, updated_at
        FROM community_chat_messages
        WHERE status = 'ACTIVE'
        ORDER BY created_at DESC, id DESC
        LIMIT ?
      ) recent
      ORDER BY created_at ASC, id ASC`)
      .bind(MAX_MESSAGES).all<CommunityChatMessageRow>();

    return privateJson({
      rows: rows.results.map((row) => responseRow(row, member)),
      limit: MAX_MESSAGES,
    });
  } catch (error) {
    return privateJson({
      error: error instanceof Error ? error.message : '이용자 라운지를 불러오지 못했습니다.',
    }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = textValue(body.farmId);
    const content = textValue(body.content);
    if (!content || Array.from(content).length > MAX_CONTENT_LENGTH) {
      return privateJson({ error: `대화 내용은 ${MAX_CONTENT_LENGTH}자 이내로 입력해 주세요.` }, { status: 422 });
    }

    const member = await approvedMemberFor(request, farmId);
    if (!member) {
      return privateJson({ error: '승인된 농장 사용자만 이용자 라운지에 참여할 수 있습니다.' }, { status: 403 });
    }

    const detected = detectSupportedLanguage(
      content,
      body.languageHint ?? body.language,
      member.preferredLanguage,
    );
    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const rateLimitCutoff = new Date(Date.now() - RATE_LIMIT_WINDOW_MS).toISOString();
    const row: CommunityChatMessageRow = {
      id,
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

    const inserted = await env.DB.prepare(`INSERT INTO community_chat_messages(
        id, author_member_id, author_name_snapshot, author_role_snapshot,
        author_account_snapshot, language, content, status, created_at, updated_at
      ) SELECT ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?
      WHERE (SELECT COUNT(*) FROM community_chat_messages
        WHERE author_member_id = ? AND created_at >= ?) < ?`)
      .bind(id, member.id, row.author_name_snapshot, member.role,
        row.author_account_snapshot, detected.language, content, now, now,
        member.id, rateLimitCutoff, RATE_LIMIT_COUNT).run();

    if (!inserted.meta.changes) {
      return privateJson(
        { error: '메시지를 너무 빠르게 보내고 있습니다. 잠시 후 다시 시도해 주세요.' },
        { status: 429, headers: { 'Retry-After': '60' } },
      );
    }

    return privateJson({
      row: responseRow(row, member),
      message: '이용자 라운지에 대화를 보냈습니다.',
    }, { status: 201 });
  } catch (error) {
    return privateJson({
      error: error instanceof Error ? error.message : '이용자 라운지에 대화를 보내지 못했습니다.',
    }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  try {
    await ensureSchema();
    const url = new URL(request.url);
    const farmId = textValue(url.searchParams.get('farmId'));
    const messageId = textValue(url.searchParams.get('messageId'));
    if (!messageId || Array.from(messageId).length > 100) {
      return privateJson({ error: '삭제할 대화를 확인해 주세요.' }, { status: 422 });
    }

    const member = await approvedMemberFor(request, farmId);
    if (!member) {
      return privateJson({ error: '승인된 농장 사용자만 대화를 삭제할 수 있습니다.' }, { status: 403 });
    }

    const existing = await env.DB.prepare(`SELECT id, author_member_id, author_name_snapshot,
        author_role_snapshot, author_account_snapshot, language, content, status, created_at, updated_at
      FROM community_chat_messages
      WHERE id = ? LIMIT 1`)
      .bind(messageId).first<CommunityChatMessageRow>();
    if (!existing || existing.status !== 'ACTIVE') {
      return privateJson({ error: '삭제할 대화를 찾지 못했습니다.' }, { status: 404 });
    }

    const isMine = existing.author_member_id === member.id;
    if (member.role !== 'ADMIN' && !isMine) {
      return privateJson({ error: '본인이 작성한 대화만 삭제할 수 있습니다.' }, { status: 403 });
    }

    const updatedAt = new Date().toISOString();
    await env.DB.prepare(`UPDATE community_chat_messages
      SET status = 'DELETED', updated_at = ?
      WHERE id = ? AND status = 'ACTIVE'`)
      .bind(updatedAt, messageId).run();

    return privateJson({
      id: messageId,
      status: 'DELETED',
      updated_at: updatedAt,
      message: '대화를 삭제했습니다.',
    });
  } catch (error) {
    return privateJson({
      error: error instanceof Error ? error.message : '대화를 삭제하지 못했습니다.',
    }, { status: 400 });
  }
}
