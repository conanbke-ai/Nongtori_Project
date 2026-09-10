import type { NoteTarget, StoredNoteScope } from '../domain/record-policy';

export async function findRecordTarget(db: D1Database, farmId: string, predictionId: string, sessionId: string): Promise<NoteTarget | null> {
  if (predictionId) {
    const prediction = await db.prepare(`SELECT fp.id, cs.id AS capture_session_id,
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
      LIMIT 1`).bind(predictionId, farmId).first<NoteTarget>();
    return prediction;
  }
  if (!sessionId) return null;
  const session = await db.prepare(`SELECT cs.id AS capture_session_id, '__SESSION__' AS track_key,
      NULL AS id, NULL AS frame_id, NULL AS frame_index, NULL AS timestamp_ms
    FROM capture_sessions cs WHERE cs.id = ? AND cs.farm_id = ?
 LIMIT 1`).bind(sessionId, farmId).first<NoteTarget>();
  return session;
}

export async function storedNoteScope(db: D1Database, noteId: string, farmId: string, captureSessionId: string) {
  return db.prepare(`SELECT mn.author_member_id, mn.target_frame_id, mn.parent_note_id,
      mn.track_key, mn.status, mn.language, mn.content, mn.updated_at,
      fp.frame_id AS evidence_frame_id
    FROM mite_record_notes mn
    LEFT JOIN frame_predictions fp ON fp.id = mn.evidence_frame_prediction_id
    WHERE mn.id = ? AND mn.farm_id = ? AND mn.capture_session_id = ? LIMIT 1`)
    .bind(noteId, farmId, captureSessionId).first<StoredNoteScope>();
}

