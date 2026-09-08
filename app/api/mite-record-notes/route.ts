import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import {
  getFarmMember,
  publicMemberAccountCode,
  publicMemberName,
  publicSnapshotName,
} from '@/app/lib/farm-auth';
import { detectSupportedLanguage } from '@/app/lib/detect-language';

export const runtime = 'edge';

const languages = new Set(['ko', 'vi', 'th', 'zh-CN']);

type Member = NonNullable<Awaited<ReturnType<typeof getFarmMember>>>;
type NoteTarget = {
  id: string | null;
  capture_session_id: string;
  frame_id: string | null;
  frame_index: number | null;
  timestamp_ms: number | null;
  track_key: string;
  house_code?: string | null;
  house_name?: string | null;
  bed_code?: string | null;
  bed_name?: string | null;
  zone_code?: string | null;
  zone_name?: string | null;
  video_modality?: string | null;
  location_source?: string | null;
};
type NoteContext = { member: Member; target: NoteTarget };
type StoredNoteScope = {
  author_member_id: string | null;
  target_frame_id: string | null;
  evidence_frame_id: string | null;
  parent_note_id: string | null;
  track_key: string;
  status: string;
  language: string;
  content: string;
  updated_at: string;
};

type StoredNoteRow = {
  id: string;
  author_member_id: string | null;
  author_name_snapshot: string;
  author_role_snapshot: string;
  author_account_snapshot: string;
  language: string;
  content: string;
  translated_content: string | null;
  detected_source_language: string | null;
  translation_source_updated_at: string | null;
  [key: string]: unknown;
};

function shortText(value: unknown, max: number) {
  const result = typeof value === 'string' ? value.trim() : '';
  if (result.length > max) throw new Error(`메모는 ${max}자 이내로 입력해 주세요.`);
  return result;
}

function publicTargetContext(target: NoteTarget) {
  if (typeof target.timestamp_ms !== 'number') return null;
  return {
    timestamp_ms: target.timestamp_ms,
    house_code: target.house_code ?? null,
    house_name: target.house_name ?? null,
    bed_code: target.bed_code ?? null,
    bed_name: target.bed_name ?? null,
    zone_code: target.zone_code ?? null,
    zone_name: target.zone_name ?? null,
    video_modality: target.video_modality ?? null,
    location_source: target.location_source ?? 'SESSION_DEFAULT',
  };
}

async function contextFor(request: Request, farmId: string, predictionId: string, sessionId: string): Promise<NoteContext | null> {
  const member = await getFarmMember(request, farmId);
  if (!member || (!member.permissions.viewHistory && !member.permissions.reviewAlerts)) return null;
  if (predictionId) {
    const prediction = await env.DB.prepare(`SELECT fp.id, cs.id AS capture_session_id,
        fp.frame_id, fr.frame_index, fr.timestamp_ms, 'frame:' || fp.frame_id AS track_key,
        CASE WHEN fla.frame_id IS NOT NULL THEN fh.code ELSE sh.code END AS house_code,
        CASE WHEN fla.frame_id IS NOT NULL THEN fh.name ELSE sh.name END AS house_name,
        CASE WHEN fla.frame_id IS NOT NULL THEN fb.code ELSE sb.code END AS bed_code,
        CASE WHEN fla.frame_id IS NOT NULL THEN fb.name ELSE sb.name END AS bed_name,
        CASE WHEN fla.frame_id IS NOT NULL THEN fz.code ELSE sz.code END AS zone_code,
        CASE WHEN fla.frame_id IS NOT NULL THEN fz.name ELSE sz.name END AS zone_name,
        CASE WHEN fla.frame_id IS NOT NULL THEN fla.source ELSE 'SESSION_DEFAULT' END AS location_source,
        CASE
          WHEN va.modality = 'DUAL_SENSOR_VIDEO' OR (
            EXISTS (SELECT 1 FROM video_assets rgb
              WHERE rgb.capture_session_id = cs.id AND rgb.modality = 'RGB_VIDEO')
            AND EXISTS (SELECT 1 FROM video_assets thermal
              WHERE thermal.capture_session_id = cs.id AND thermal.modality = 'THERMAL_VIDEO')
          ) THEN 'DUAL_SENSOR_VIDEO'
          WHEN va.modality = 'THERMAL_VIDEO' THEN 'THERMAL_VIDEO'
          ELSE 'RGB_VIDEO'
        END AS video_modality
      FROM frame_predictions fp
      JOIN inference_runs ir ON ir.id = fp.inference_run_id
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN video_assets va ON va.id = fr.video_asset_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id AND cs.id = ir.capture_session_id
      LEFT JOIN frame_location_assignments fla ON fla.frame_id = fr.id AND fla.farm_id = cs.farm_id
      LEFT JOIN houses fh ON fh.id = fla.house_id AND fh.farm_id = cs.farm_id
      LEFT JOIN beds fb ON fb.id = fla.bed_id AND fb.house_id = fh.id
      LEFT JOIN zones fz ON fz.id = fla.zone_id AND fz.bed_id = fb.id
      LEFT JOIN houses sh ON sh.id = cs.house_id AND sh.farm_id = cs.farm_id
      LEFT JOIN beds sb ON sb.id = cs.bed_id AND sb.house_id = sh.id
      LEFT JOIN zones sz ON sz.id = cs.zone_id AND sz.bed_id = sb.id
      WHERE fp.id = ? AND cs.farm_id = ?
        AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
      LIMIT 1`).bind(predictionId, farmId).first<NoteTarget>();
    return prediction ? { member, target: prediction } : null;
  }
  if (!sessionId) return null;
  const session = await env.DB.prepare(`SELECT cs.id AS capture_session_id, '__SESSION__' AS track_key,
      NULL AS id, NULL AS frame_id, NULL AS frame_index, NULL AS timestamp_ms
    FROM capture_sessions cs WHERE cs.id = ? AND cs.farm_id = ?
    AND (
      EXISTS (SELECT 1 FROM capture_assets ca WHERE ca.capture_session_id = cs.id
        AND ca.modality IN ('LEAF_RGB', 'LEAF_THERMAL'))
      OR EXISTS (SELECT 1 FROM video_assets va WHERE va.capture_session_id = cs.id
        AND va.modality IN ('RGB_VIDEO', 'THERMAL_VIDEO', 'DUAL_SENSOR_VIDEO'))
      OR EXISTS (SELECT 1 FROM inference_runs ir WHERE ir.capture_session_id = cs.id
        AND upper(ir.task) LIKE '%MITE%')
    ) LIMIT 1`).bind(sessionId, farmId).first<NoteTarget>();
  return session ? { member, target: session } : null;
}

async function storedNoteScope(noteId: string, farmId: string, captureSessionId: string) {
  return env.DB.prepare(`SELECT mn.author_member_id, mn.target_frame_id, mn.parent_note_id,
      mn.track_key, mn.status, mn.language, mn.content, mn.updated_at,
      fp.frame_id AS evidence_frame_id
    FROM mite_record_notes mn
    LEFT JOIN frame_predictions fp ON fp.id = mn.evidence_frame_prediction_id
    WHERE mn.id = ? AND mn.farm_id = ? AND mn.capture_session_id = ? LIMIT 1`)
    .bind(noteId, farmId, captureSessionId).first<StoredNoteScope>();
}

function belongsToTarget(note: StoredNoteScope, target: NoteTarget) {
  if (target.frame_id) return note.target_frame_id === target.frame_id || note.evidence_frame_id === target.frame_id;
  return !note.target_frame_id && note.track_key === '__SESSION__';
}

function normalizedLanguage(value: string | null | undefined) {
  const normalized = value?.trim().toLowerCase();
  if (normalized === 'zh' || normalized === 'zh-cn') return 'zh-CN';
  if (normalized === 'ko' || normalized === 'vi' || normalized === 'th') return normalized;
  return null;
}

async function translateWithGoogle(contents: string[], targetLanguage: string) {
  const apiKey = (env as Cloudflare.Env).GOOGLE_TRANSLATE_API_KEY?.trim();
  if (!apiKey) return null;
  const response = await fetch('https://translation.googleapis.com/language/translate/v2', {
    method: 'POST',
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'x-goog-api-key': apiKey,
    },
    body: JSON.stringify({ q: contents, target: targetLanguage, format: 'text' }),
  });
  if (!response.ok) throw new Error('TRANSLATION_PROVIDER_FAILED');
  const result = await response.json() as {
    data?: { translations?: Array<{ translatedText?: string; detectedSourceLanguage?: string; model?: string }> };
  };
  const translations = result.data?.translations ?? [];
  if (translations.length !== contents.length) throw new Error('TRANSLATION_RESULT_MISMATCH');
  const normalized = translations.map((translation) => ({
    content: translation.translatedText?.trim() ?? '',
    detectedSourceLanguage: translation.detectedSourceLanguage?.trim() || null,
    model: translation.model?.trim() || 'nmt',
  }));
  if (normalized.some((translation) => !translation.content)) throw new Error('TRANSLATION_RESULT_MISMATCH');
  return normalized;
}

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farmId = url.searchParams.get('farmId')?.trim() ?? '';
  const predictionId = url.searchParams.get('predictionId')?.trim() ?? '';
  const sessionId = url.searchParams.get('sessionId')?.trim() ?? '';
  const mode = url.searchParams.get('mode')?.trim() ?? '';
  const targetLanguage = url.searchParams.get('language')?.trim() || 'ko';
  if (!farmId || (!predictionId && !sessionId)) {
    return NextResponse.json({ error: '메모를 확인할 응애 예찰 기록을 선택해 주세요.' }, { status: 400 });
  }
  if (!languages.has(targetLanguage)) {
    return NextResponse.json({ error: '지원하는 표시 언어를 선택해 주세요.' }, { status: 422 });
  }

  if (mode === 'frames') {
    if (!sessionId || predictionId) return NextResponse.json({ error: '영상 기록을 선택해 주세요.' }, { status: 422 });
    const context = await contextFor(request, farmId, '', sessionId);
    if (!context) return NextResponse.json({ error: '이 영상의 확인 지점을 볼 권한이 없습니다.' }, { status: 403 });
    const frames = await env.DB.prepare(`WITH ranked AS (
        SELECT fp.id AS prediction_id, fp.frame_id, fr.frame_index, fr.timestamp_ms,
          CASE
            WHEN va.modality = 'DUAL_SENSOR_VIDEO' OR (
              EXISTS (SELECT 1 FROM video_assets rgb
                WHERE rgb.capture_session_id = cs.id AND rgb.modality = 'RGB_VIDEO')
              AND EXISTS (SELECT 1 FROM video_assets thermal
                WHERE thermal.capture_session_id = cs.id AND thermal.modality = 'THERMAL_VIDEO')
            ) THEN 'DUAL_SENSOR_VIDEO'
            WHEN va.modality = 'THERMAL_VIDEO' THEN 'THERMAL_VIDEO'
            ELSE 'RGB_VIDEO'
          END AS video_modality,
          fp.class_label, fp.confidence,
          CASE WHEN fla.frame_id IS NOT NULL THEN fh.code ELSE sh.code END AS house_code,
          CASE WHEN fla.frame_id IS NOT NULL THEN fh.name ELSE sh.name END AS house_name,
          CASE WHEN fla.frame_id IS NOT NULL THEN fb.code ELSE sb.code END AS bed_code,
          CASE WHEN fla.frame_id IS NOT NULL THEN fb.name ELSE sb.name END AS bed_name,
          CASE WHEN fla.frame_id IS NOT NULL THEN fz.code ELSE sz.code END AS zone_code,
          CASE WHEN fla.frame_id IS NOT NULL THEN fz.name ELSE sz.name END AS zone_name,
          CASE WHEN fla.frame_id IS NOT NULL THEN fla.source ELSE 'SESSION_DEFAULT' END AS location_source,
          ROW_NUMBER() OVER (
            PARTITION BY fp.frame_id
            ORDER BY COALESCE(fp.confidence, -1) DESC, fp.created_at DESC, fp.id DESC
          ) AS frame_rank
        FROM frame_predictions fp
        JOIN inference_runs ir ON ir.id = fp.inference_run_id
        JOIN frames fr ON fr.id = fp.frame_id
        JOIN video_assets va ON va.id = fr.video_asset_id
        JOIN capture_sessions cs ON cs.id = fr.capture_session_id AND cs.id = ir.capture_session_id
        LEFT JOIN frame_location_assignments fla ON fla.frame_id = fr.id AND fla.farm_id = cs.farm_id
        LEFT JOIN houses fh ON fh.id = fla.house_id AND fh.farm_id = cs.farm_id
        LEFT JOIN beds fb ON fb.id = fla.bed_id AND fb.house_id = fh.id
        LEFT JOIN zones fz ON fz.id = fla.zone_id AND fz.bed_id = fb.id
        LEFT JOIN houses sh ON sh.id = cs.house_id AND sh.farm_id = cs.farm_id
        LEFT JOIN beds sb ON sb.id = cs.bed_id AND sb.house_id = sh.id
        LEFT JOIN zones sz ON sz.id = cs.zone_id AND sz.bed_id = sb.id
        WHERE cs.id = ? AND cs.farm_id = ?
          AND (upper(ir.task) LIKE '%MITE%' OR upper(fp.class_label) LIKE '%MITE%' OR fp.class_label LIKE '%응애%')
      )
      SELECT ranked.prediction_id, ranked.frame_id, ranked.frame_index, ranked.timestamp_ms,
        ranked.video_modality,
        ranked.class_label, ranked.confidence,
        ranked.house_code, ranked.house_name, ranked.bed_code, ranked.bed_name,
        ranked.zone_code, ranked.zone_name, ranked.location_source,
        (SELECT COUNT(*) FROM mite_record_notes mn
          WHERE mn.farm_id = ? AND mn.capture_session_id = ? AND mn.status = 'ACTIVE'
            AND (mn.target_frame_id = ranked.frame_id OR mn.evidence_frame_prediction_id IN (
              SELECT fp2.id FROM frame_predictions fp2 WHERE fp2.frame_id = ranked.frame_id
            ))) AS note_count
      FROM ranked WHERE ranked.frame_rank = 1
      ORDER BY ranked.timestamp_ms, ranked.frame_index LIMIT 200`)
      .bind(sessionId, farmId, farmId, sessionId).all<{
        prediction_id: string;
        frame_id: string;
        frame_index: number;
        timestamp_ms: number;
        class_label: string;
        confidence: number | null;
        note_count: number;
        house_code: string | null;
        house_name: string | null;
        bed_code: string | null;
        bed_name: string | null;
        zone_code: string | null;
        zone_name: string | null;
        video_modality: string | null;
        location_source: string;
      }>();
    const messageCount = frames.results.reduce((sum, frame) => sum + Number(frame.note_count || 0), 0);
    return NextResponse.json({ frames: frames.results, messageCount });
  }

  const context = await contextFor(request, farmId, predictionId, sessionId);
  if (!context) return NextResponse.json({ error: '이 예찰 기록의 메모를 볼 권한이 없습니다.' }, { status: 403 });

  const baseSelect = `SELECT mn.id, mn.parent_note_id, mn.author_member_id,
      mn.author_name_snapshot, mn.author_role_snapshot, mn.author_account_snapshot,
      mn.language, mn.content, mn.created_at, mn.updated_at,
      mnt.translated_content, mnt.detected_source_language,
      mnt.source_updated_at AS translation_source_updated_at
    FROM mite_record_notes mn
    LEFT JOIN mite_record_note_translations mnt
      ON mnt.note_id = mn.id AND mnt.target_language = ?
        AND mnt.source_updated_at = mn.updated_at`;
  const rows = context.target.frame_id
    ? await env.DB.prepare(`${baseSelect}
        WHERE mn.farm_id = ? AND mn.capture_session_id = ? AND mn.status = 'ACTIVE'
          AND (mn.target_frame_id = ? OR mn.evidence_frame_prediction_id IN (
            SELECT fp.id FROM frame_predictions fp WHERE fp.frame_id = ?
          ))
        ORDER BY mn.created_at, mn.id LIMIT 200`)
      .bind(targetLanguage, farmId, context.target.capture_session_id, context.target.frame_id, context.target.frame_id)
      .all<StoredNoteRow>()
    : await env.DB.prepare(`${baseSelect}
        WHERE mn.farm_id = ? AND mn.capture_session_id = ? AND mn.track_key = '__SESSION__'
          AND mn.target_frame_id IS NULL AND mn.status = 'ACTIVE'
        ORDER BY mn.created_at, mn.id LIMIT 200`)
      .bind(targetLanguage, farmId, context.target.capture_session_id)
      .all<StoredNoteRow>();
  return NextResponse.json({
    targetContext: publicTargetContext(context.target),
    rows: rows.results.map((row) => {
      const {
        author_member_id: authorMemberId,
        ...publicRow
      } = row;
      const accountCode = publicMemberAccountCode({
        id: authorMemberId,
        farmId,
        role: row.author_role_snapshot,
      });
      const translatedContent = typeof row.translated_content === 'string' && row.translated_content.trim()
        ? row.translated_content
        : null;
      const detectedSourceLanguage = normalizedLanguage(row.detected_source_language);
      const isOriginalLanguage = translatedContent
        ? detectedSourceLanguage === targetLanguage
        : row.language === targetLanguage;
      return {
        ...publicRow,
        author_name_snapshot: publicSnapshotName(row.author_name_snapshot, {
          accountCode,
          memberId: authorMemberId,
          farmId,
          role: row.author_role_snapshot,
        }),
        author_account_snapshot: accountCode,
        display_content: isOriginalLanguage ? row.content : translatedContent || row.content,
        display_language: translatedContent ? targetLanguage : row.language,
        translation_status: isOriginalLanguage ? 'original' : translatedContent ? 'translated' : 'unavailable',
        is_mine: Boolean(context.member.id && authorMemberId === context.member.id),
        can_edit: Boolean(context.member.id && authorMemberId === context.member.id),
        can_delete: context.member.permissions.manageMembers || Boolean(context.member.id && authorMemberId === context.member.id),
      };
    }),
  });
}

export async function POST(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const action = shortText(body.action, 40);
    const farmId = shortText(body.farmId, 100);
    const predictionId = shortText(body.predictionId, 100);
    const sessionId = shortText(body.sessionId, 100);
    if (action === 'TRANSLATE_NOTES') {
      const targetLanguage = shortText(body.targetLanguage, 10);
      const noteIds = Array.isArray(body.noteIds)
        ? [...new Set(body.noteIds.map((value) => shortText(value, 100)).filter(Boolean))]
        : [];
      if (!farmId || (!predictionId && !sessionId) || !languages.has(targetLanguage)
        || !noteIds.length || noteIds.length > 20) {
        return NextResponse.json({ error: '번역할 의견을 확인해 주세요.' }, { status: 422 });
      }
      const context = await contextFor(request, farmId, predictionId, sessionId);
      if (!context) {
        return NextResponse.json({ error: '이 기록의 의견을 볼 권한이 없습니다.' }, { status: 403 });
      }
      const notes = (await Promise.all(noteIds.map((noteId) => storedNoteScope(
        noteId,
        farmId,
        context.target.capture_session_id,
      )))).filter((note): note is StoredNoteScope => Boolean(
        note && note.status === 'ACTIVE' && belongsToTarget(note, context.target),
      ));
      if (notes.length !== noteIds.length || notes.reduce((sum, note) => sum + note.content.length, 0) > 6000) {
        return NextResponse.json({ error: '같은 확인 지점의 의견만 번역할 수 있습니다.' }, { status: 422 });
      }
      const translated = await translateWithGoogle(notes.map((note) => note.content), targetLanguage);
      if (!translated) {
        return NextResponse.json({
          error: '공용 번역 서비스가 아직 연결되지 않았습니다.',
          translationUnavailable: true,
        }, { status: 503 });
      }
      const now = new Date().toISOString();
      const storedTranslations = await env.DB.batch(notes.map((note, index) => env.DB.prepare(`INSERT INTO mite_record_note_translations(
          id, note_id, source_language, target_language, source_updated_at,
          translated_content, detected_source_language, provider, model_version, created_at, updated_at
        ) SELECT ?, current.id, ?, ?, current.updated_at, ?, ?, 'GOOGLE_TRANSLATE_V2', ?, ?, ?
        FROM mite_record_notes current
        WHERE current.id = ? AND current.updated_at = ? AND current.content = ? AND current.status = 'ACTIVE'
        ON CONFLICT(note_id, target_language) DO UPDATE SET
          source_language = excluded.source_language,
          detected_source_language = excluded.detected_source_language,
          source_updated_at = excluded.source_updated_at,
          translated_content = excluded.translated_content,
          provider = excluded.provider,
          model_version = excluded.model_version,
          updated_at = excluded.updated_at`)
        .bind(crypto.randomUUID(), note.language, targetLanguage,
          translated[index].content, translated[index].detectedSourceLanguage,
          translated[index].model, now, now, noteIds[index], note.updated_at, note.content)));
      return NextResponse.json({
        translations: noteIds.flatMap((noteId, index) => storedTranslations[index].meta.changes ? [{
          note_id: noteId,
          translated_content: translated[index].content,
          display_language: targetLanguage,
          detected_source_language: translated[index].detectedSourceLanguage,
          source_updated_at: notes[index].updated_at,
        }] : []),
      });
    }
    const parentNoteId = shortText(body.parentNoteId, 100);
    const content = shortText(body.content, 600);
    const languageHint = shortText(body.languageHint ?? body.language, 10);
    if (!farmId || (!predictionId && !sessionId) || !content || (languageHint && !languages.has(languageHint))) {
      return NextResponse.json({ error: '메모 내용을 확인해 주세요.' }, { status: 422 });
    }
    const context = await contextFor(request, farmId, predictionId, sessionId);
    if (!context?.member.permissions.reviewAlerts) {
      return NextResponse.json({ error: '이 예찰 기록에 메모를 남길 권한이 없습니다.' }, { status: 403 });
    }
    const detected = detectSupportedLanguage(content, languageHint, context.member.preferredLanguage);

    let rootParentId: string | null = null;
    if (parentNoteId) {
      const parent = await storedNoteScope(parentNoteId, farmId, context.target.capture_session_id);
      if (!parent || parent.status !== 'ACTIVE' || !belongsToTarget(parent, context.target)) {
        return NextResponse.json({ error: '같은 확인 지점의 메모에만 답글을 남길 수 있습니다.' }, { status: 422 });
      }
      rootParentId = parent.parent_note_id || parentNoteId;
    }

    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    await env.DB.prepare(`INSERT INTO mite_record_notes(
      id, farm_id, capture_session_id, track_key, target_frame_id,
      evidence_frame_prediction_id, parent_note_id, author_member_id,
      author_name_snapshot, author_role_snapshot, author_account_snapshot,
      language, content, status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)`)
      .bind(id, farmId, context.target.capture_session_id, context.target.track_key,
        context.target.frame_id, context.target.id, rootParentId, context.member.id,
        publicMemberName(context.member), context.member.role, publicMemberAccountCode(context.member),
        detected.language, content, now, now).run();
    return NextResponse.json({ id, parentNoteId: rootParentId, language: detected.language,
      detection_method: detected.method, detection_confidence: detected.confidence,
      message: '확인 지점에 공유 의견을 남겼습니다.' }, { status: 201 });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '메모를 저장하지 못했습니다.' }, { status: 400 });
  }
}

export async function PATCH(request: Request) {
  try {
    await ensureSchema();
    const body = await request.json() as Record<string, unknown>;
    const farmId = shortText(body.farmId, 100);
    const predictionId = shortText(body.predictionId, 100);
    const sessionId = shortText(body.sessionId, 100);
    const noteId = shortText(body.noteId, 100);
    const content = shortText(body.content, 600);
    const languageHint = shortText(body.languageHint ?? body.language, 10);
    if (!farmId || (!predictionId && !sessionId) || !noteId || !content || (languageHint && !languages.has(languageHint))) {
      return NextResponse.json({ error: '수정할 메모 내용을 확인해 주세요.' }, { status: 422 });
    }
    const context = await contextFor(request, farmId, predictionId, sessionId);
    if (!context?.member.id) return NextResponse.json({ error: '메모를 수정할 권한이 없습니다.' }, { status: 403 });
    const existing = await storedNoteScope(noteId, farmId, context.target.capture_session_id);
    if (!existing || existing.status !== 'ACTIVE' || existing.author_member_id !== context.member.id || !belongsToTarget(existing, context.target)) {
      return NextResponse.json({ error: '본인이 작성한 같은 확인 지점의 메모만 수정할 수 있습니다.' }, { status: 403 });
    }
    const detected = detectSupportedLanguage(content, languageHint, context.member.preferredLanguage);
    const now = new Date().toISOString();
    await env.DB.batch([
      env.DB.prepare(`UPDATE mite_record_notes SET content = ?, language = ?, updated_at = ?
        WHERE id = ? AND farm_id = ? AND author_member_id = ? AND status = 'ACTIVE'`)
        .bind(content, detected.language, now, noteId, farmId, context.member.id),
      env.DB.prepare('DELETE FROM mite_record_note_translations WHERE note_id = ?').bind(noteId),
    ]);
    return NextResponse.json({ language: detected.language, detection_method: detected.method,
      detection_confidence: detected.confidence, message: '공유 메모를 수정했습니다.' });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : '메모를 수정하지 못했습니다.' }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farmId = url.searchParams.get('farmId')?.trim() ?? '';
  const predictionId = url.searchParams.get('predictionId')?.trim() ?? '';
  const sessionId = url.searchParams.get('sessionId')?.trim() ?? '';
  const noteId = url.searchParams.get('noteId')?.trim() ?? '';
  const context = await contextFor(request, farmId, predictionId, sessionId);
  if (!context) return NextResponse.json({ error: '메모를 삭제할 권한이 없습니다.' }, { status: 403 });
  const existing = await storedNoteScope(noteId, farmId, context.target.capture_session_id);
  if (!existing || existing.status !== 'ACTIVE' || !belongsToTarget(existing, context.target)
    || (!context.member.permissions.manageMembers && existing.author_member_id !== context.member.id)) {
    return NextResponse.json({ error: '본인 또는 농장 관리 권한이 있는 사용자만 삭제할 수 있습니다.' }, { status: 403 });
  }
  await env.DB.prepare(`UPDATE mite_record_notes SET status = 'DELETED', updated_at = ?
    WHERE id = ? AND farm_id = ? AND status = 'ACTIVE'`)
    .bind(new Date().toISOString(), noteId, farmId).run();
  return NextResponse.json({ message: '공유 메모를 삭제했습니다.' });
}
