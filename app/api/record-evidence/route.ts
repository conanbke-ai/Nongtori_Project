import { env } from 'cloudflare:workers';
import { NextResponse } from 'next/server';
import { ensureSchema } from '@/db';
import { getFarmMember } from '@/app/lib/farm-auth';

export const runtime = 'edge';

export async function GET(request: Request) {
  await ensureSchema();
  const url = new URL(request.url);
  const farmId = url.searchParams.get('farmId')?.trim() ?? '';
  const predictionId = url.searchParams.get('predictionId')?.trim() ?? '';
  const sessionId = url.searchParams.get('sessionId')?.trim() ?? '';
  const modality = url.searchParams.get('modality') === 'thermal' ? 'LEAF_THERMAL' : 'LEAF_RGB';
  if (!farmId || (!predictionId && !sessionId)) {
    return NextResponse.json({ error: '확인할 사진 기록을 선택해 주세요.' }, { status: 400 });
  }
  const member = await getFarmMember(request, farmId);
  if (!member || (!member.permissions.viewHistory && !member.permissions.reviewAlerts)) {
    return NextResponse.json({ error: '이 사진을 볼 권한이 없습니다.' }, { status: 403 });
  }

  let row: { object_key: string | null; content_type: string | null } | null;
  if (predictionId) {
    row = await env.DB.prepare(`SELECT
        CASE WHEN ? = 'LEAF_THERMAL' THEN (
          SELECT ca.object_key FROM capture_assets ca
          WHERE ca.capture_session_id = cs.id AND ca.modality = 'LEAF_THERMAL' LIMIT 1
        ) ELSE COALESCE(fr.object_key, (
          SELECT ca.object_key FROM capture_assets ca
          WHERE ca.capture_session_id = cs.id AND ca.modality = 'LEAF_RGB' LIMIT 1
        )) END AS object_key,
        CASE WHEN ? = 'LEAF_THERMAL' THEN (
          SELECT ca.content_type FROM capture_assets ca
          WHERE ca.capture_session_id = cs.id AND ca.modality = 'LEAF_THERMAL' LIMIT 1
        ) ELSE COALESCE((
          SELECT ca.content_type FROM capture_assets ca
          WHERE ca.capture_session_id = cs.id AND ca.modality = 'LEAF_RGB' LIMIT 1
        ), 'image/jpeg') END AS content_type
      FROM frame_predictions fp
      JOIN inference_runs ir ON ir.id = fp.inference_run_id
      JOIN frames fr ON fr.id = fp.frame_id
      JOIN capture_sessions cs ON cs.id = fr.capture_session_id AND cs.id = ir.capture_session_id
      WHERE fp.id = ? AND cs.farm_id = ?
      LIMIT 1`).bind(modality, modality, predictionId, farmId)
      .first<{ object_key: string | null; content_type: string | null }>();
  } else {
    row = await env.DB.prepare(`SELECT ca.object_key, ca.content_type
      FROM capture_assets ca JOIN capture_sessions cs ON cs.id = ca.capture_session_id
      WHERE cs.id = ? AND cs.farm_id = ? AND ca.modality = ? LIMIT 1`)
      .bind(sessionId, farmId, modality).first<{ object_key: string | null; content_type: string | null }>();
  }
  if (!row?.object_key) return NextResponse.json({ error: '표시할 사진이 없습니다.' }, { status: 404 });
  const object = await env.FILES.get(row.object_key);
  if (!object?.body) return NextResponse.json({ error: '사진 파일을 찾지 못했습니다.' }, { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('content-type', row.content_type?.startsWith('image/') ? row.content_type : 'image/jpeg');
  headers.set('cache-control', 'private, no-store');
  headers.set('content-disposition', 'inline');
  headers.set('x-content-type-options', 'nosniff');
  return new Response(object.body, { headers });
}
