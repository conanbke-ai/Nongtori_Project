import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember, publicMemberName, publicSnapshotName } from '@/app/lib/farm-auth';

export const runtime = 'edge';

const verdicts = new Set(['MITE_CONFIRMED', 'NOT_MITE', 'RECHECK']);
const quickNotes = new Set(['', 'LEAF_BACK_CHECKED', 'WEBBING_SEEN', 'LEAF_DAMAGE_ONLY', 'PHOTO_NEEDED']);
const languages = new Set(['ko', 'vi', 'th', 'zh-CN']);

type ReviewRow = {
  id: string;
  verdict: string;
  quick_note_code: string | null;
  note: string;
  note_language: string;
  reviewer_member_id: string | null;
  reviewer_name: string | null;
  reviewer_role: string | null;
  created_at: string;
};

function shortText(value: unknown, max: number) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error(`메모는 ${max}자 이내로 입력해 주세요.`);
  return result;
}

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farmId = url.searchParams.get('farmId')?.trim() ?? '';
  const predictionId = url.searchParams.get('predictionId')?.trim() ?? '';
  if (!farmId || !predictionId) return NextResponse.json({ error: '확인할 알림을 선택해 주세요.' }, { status: 400 });
  const member = await getFarmMember(request, farmId);
  if (!member?.permissions.reviewAlerts) return NextResponse.json({ error: '현장 확인 기록을 볼 권한이 없습니다.' }, { status: 403 });
  const prediction = await env.DB.prepare(`SELECT fp.id, fp.inference_run_id, fp.track_id FROM frame_predictions fp
    JOIN inference_runs ir ON ir.id = fp.inference_run_id
    JOIN frames fr ON fr.id = fp.frame_id
    JOIN capture_sessions cs ON cs.id = fr.capture_session_id
    WHERE fp.id = ? AND cs.farm_id = ?
      AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
    LIMIT 1`).bind(predictionId, farmId).first<{
      id: string;
      inference_run_id: string;
      track_id: string | null;
    }>();
  if (!prediction) return NextResponse.json({ error: '이 농장의 알림이 아닙니다.' }, { status: 404 });
  const rows = await env.DB.prepare(`SELECT pre.id, pre.verdict, pre.quick_note_code,
      pre.note, pre.note_language, pre.reviewer_member_id,
      pre.reviewer_name_snapshot AS reviewer_name,
      pre.reviewer_role_snapshot AS reviewer_role, pre.created_at
    FROM prediction_review_events pre
    JOIN frame_predictions reviewed_fp ON reviewed_fp.id = pre.frame_prediction_id
    WHERE pre.farm_id = ? AND reviewed_fp.inference_run_id = ?
      AND ((? IS NOT NULL AND reviewed_fp.track_id = ?)
        OR (? IS NULL AND reviewed_fp.id = ?))
    ORDER BY pre.created_at DESC, pre.id DESC LIMIT 30`)
    .bind(farmId, prediction.inference_run_id,
      prediction.track_id, prediction.track_id, prediction.track_id, prediction.id).all<ReviewRow>();
  return NextResponse.json({
    rows: rows.results.map((row) => {
      const { reviewer_member_id: reviewerMemberId, ...publicRow } = row;
      return {
        ...publicRow,
        reviewer_name: publicSnapshotName(row.reviewer_name, {
          memberId: reviewerMemberId,
          farmId,
          role: row.reviewer_role,
        }),
      };
    }),
  });
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = shortText(body.farmId, 100);
    const predictionId = shortText(body.predictionId, 100);
    const verdict = shortText(body.verdict, 40);
    const quickNoteCode = shortText(body.quickNoteCode, 40);
    const note = shortText(body.note, 300);
    const noteLanguage = shortText(body.noteLanguage, 10) || 'ko';
    if (!farmId || !predictionId || !verdicts.has(verdict)
      || !quickNotes.has(quickNoteCode) || !languages.has(noteLanguage)) {
      return NextResponse.json({ error: '현장 확인 결과를 다시 선택해 주세요.' }, { status: 422 });
    }

    const member = await getFarmMember(request, farmId);
    if (!member?.permissions.reviewAlerts) {
      return NextResponse.json({ error: '현장 확인 결과를 남길 권한이 없습니다.' }, { status: 403 });
    }
    const prediction = await env.DB.prepare(`SELECT fp.id FROM frame_predictions fp
      JOIN inference_runs ir ON ir.id = fp.inference_run_id
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id
      WHERE fp.id = ? AND cs.farm_id = ?
        AND fp.decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED')
        AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
      LIMIT 1`)
      .bind(predictionId, farmId).first();
    if (!prediction) return NextResponse.json({ error: '확인할 수 있는 응애 알림이 아닙니다.' }, { status: 404 });

    const now = new Date().toISOString();
    const reviewerName = publicMemberName(member);
    await env.DB.prepare(`INSERT INTO prediction_review_events(
      id, farm_id, frame_prediction_id, reviewer_member_id,
      reviewer_name_snapshot, reviewer_role_snapshot, verdict, quick_note_code,
      note, note_language, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(crypto.randomUUID(), farmId, predictionId, member.id, reviewerName, member.role,
        verdict, quickNoteCode || null, note, noteLanguage, now).run();

    const message = verdict === 'MITE_CONFIRMED'
      ? '응애로 확인한 기록을 남겼습니다.'
      : verdict === 'NOT_MITE'
        ? '응애가 아닌 것으로 확인한 기록을 남겼습니다.'
        : '다시 살펴볼 알림으로 남겼습니다.';
    return NextResponse.json({ verdict, reviewerName, reviewedAt: now, message }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '현장 확인 기록을 저장하지 못했습니다.' }, { status: 400 });
  }
}
