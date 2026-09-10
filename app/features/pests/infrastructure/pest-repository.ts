import { pestCodeSql } from './classification-sql';

export type PestAlertRow = {
  id: string; pest_code: string; item_id: string | null; item_name: string | null;
  crop_name: string | null; cultivar_name: string | null; class_label: string;
  confidence: number | null; decision_status: string; created_at: string;
  house_name: string | null; bed_name: string | null; zone_name: string | null;
  review_verdict: string | null; review_quick_note_code: string | null;
  review_note: string | null; review_note_language: string | null;
  reviewer_member_id: string | null; reviewer_name: string | null;
  reviewer_role: string | null; reviewed_at: string | null;
};

// The same CTE defines list, counts and review targets so filters cannot disagree.
export const pestCasesSql = `WITH classified AS (
  SELECT fp.*, cs.farm_id, cs.item_id, cs.house_id, cs.bed_id, cs.zone_id,
    ${pestCodeSql()} AS pest_code
  FROM frame_predictions fp JOIN inference_runs ir ON ir.id = fp.inference_run_id
  JOIN frames fr ON fr.id = fp.frame_id
  JOIN capture_sessions cs ON cs.id = fr.capture_session_id AND cs.id = ir.capture_session_id
  WHERE cs.farm_id = ? AND cs.source_type != 'ROBOT'
), ranked AS (
  SELECT classified.*, ROW_NUMBER() OVER (
    PARTITION BY inference_run_id, COALESCE(track_id, id), pest_code
    ORDER BY COALESCE(confidence, 0) DESC, created_at, id
  ) AS case_rank FROM classified
  WHERE pest_code IS NOT NULL AND decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED', 'PEST_REVIEW_REQUIRED', 'DISEASE_REVIEW_REQUIRED')
), cases AS (
  SELECT ranked.*, pre.verdict AS review_verdict, pre.quick_note_code AS review_quick_note_code,
    pre.note AS review_note, pre.note_language AS review_note_language, pre.reviewer_member_id,
    pre.reviewer_name_snapshot AS reviewer_name, pre.reviewer_role_snapshot AS reviewer_role,
    pre.created_at AS reviewed_at,
    CASE WHEN pre.verdict IN ('MITE_CONFIRMED', 'NOT_MITE', 'TARGET_CONFIRMED', 'NOT_TARGET') THEN 'DONE' ELSE 'OPEN' END AS review_status
  FROM ranked LEFT JOIN prediction_review_events pre ON pre.id = (
    SELECT event.id FROM prediction_review_events event JOIN classified reviewed ON reviewed.id = event.frame_prediction_id
    WHERE event.farm_id = ranked.farm_id AND reviewed.inference_run_id = ranked.inference_run_id
      AND reviewed.pest_code = ranked.pest_code
      AND ((ranked.track_id IS NOT NULL AND reviewed.track_id = ranked.track_id)
        OR (ranked.track_id IS NULL AND reviewed.id = ranked.id))
    ORDER BY event.created_at DESC, event.id DESC LIMIT 1
  ) WHERE case_rank = 1
)`;

export class PestRepository {
  constructor(private db: D1Database) {}

  async counts(farmId: string) {
    return (await this.db.prepare(`${pestCasesSql}
      SELECT pest_code, review_status, COUNT(*) AS count FROM cases GROUP BY pest_code, review_status`)
      .bind(farmId).all<{ pest_code: string; review_status: string; count: number }>()).results;
  }

  async list(farmId: string, code: string, status: string, limit: number, offset: number) {
    return (await this.db.prepare(`${pestCasesSql}
      SELECT cases.*, fi.display_name AS item_name, ct.display_name_ko AS crop_name,
        cv.display_name_ko AS cultivar_name, h.name AS house_name, b.name AS bed_name, z.name AS zone_name
      FROM cases LEFT JOIN farm_items fi ON fi.id = cases.item_id AND fi.farm_id = cases.farm_id
      LEFT JOIN crop_types ct ON ct.code = fi.crop_code LEFT JOIN cultivars cv ON cv.code = fi.cultivar_code
      LEFT JOIN houses h ON h.id = cases.house_id AND h.farm_id = cases.farm_id
      LEFT JOIN beds b ON b.id = cases.bed_id AND b.house_id = h.id
      LEFT JOIN zones z ON z.id = cases.zone_id AND z.bed_id = b.id
      WHERE (? = '' OR pest_code = ?) AND review_status = ?
      ORDER BY cases.created_at DESC, cases.id DESC LIMIT ? OFFSET ?`)
      .bind(farmId, code, code, status, limit, offset).all<PestAlertRow>()).results;
  }

  async target(farmId: string, predictionId: string) {
    return this.db.prepare(`${pestCasesSql} SELECT * FROM classified WHERE id = ? AND pest_code IS NOT NULL
      AND decision_status IN ('ALERT', 'REVIEW_REQUIRED', 'MITE_REVIEW_REQUIRED', 'PEST_REVIEW_REQUIRED', 'DISEASE_REVIEW_REQUIRED')`)
      .bind(farmId, predictionId).first<{ id: string; pest_code: string; inference_run_id: string; track_id: string | null }>();
  }

  async addReview(input: { farmId: string; predictionId: string; memberId: string; name: string; role: string; verdict: string; quickNote: string; note: string; language: string; now: string }) {
    return this.db.prepare(`INSERT INTO prediction_review_events(id, farm_id, frame_prediction_id, reviewer_member_id,
      reviewer_name_snapshot, reviewer_role_snapshot, verdict, quick_note_code, note, note_language, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(crypto.randomUUID(), input.farmId, input.predictionId, input.memberId, input.name, input.role,
        input.verdict, input.quickNote || null, input.note, input.language, input.now).run();
  }
}
