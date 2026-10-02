import type { WeightObservation, WeightSource } from '../domain/weight-source';

type WeightObservationRow = {
  id: string;
  fruit_assessment_id: string;
  source: WeightSource;
  weight_g: number;
  confidence: number | null;
  model_name: string | null;
  model_version: string | null;
  source_ref: string | null;
  measured_at: string | null;
  created_by_member_id: string | null;
  created_at: string;
};

function mapRow(row: WeightObservationRow): WeightObservation {
  return {
    id: row.id,
    fruitAssessmentId: row.fruit_assessment_id,
    source: row.source,
    weightG: Number(row.weight_g),
    confidence: row.confidence === null ? null : Number(row.confidence),
    modelName: row.model_name,
    modelVersion: row.model_version,
    sourceRef: row.source_ref,
    measuredAt: row.measured_at,
    createdByMemberId: row.created_by_member_id,
    createdAt: row.created_at,
  };
}

export class WeightObservationRepository {
  constructor(private db: D1Database) {}

  async assessment(farmId: string, assessmentId: string) {
    return this.db.prepare(`SELECT id, farm_id, capture_session_id, cultivar, capture_at
      FROM fruit_assessments WHERE id = ? AND farm_id = ?`)
      .bind(assessmentId, farmId)
      .first<{
        id: string;
        farm_id: string;
        capture_session_id: string | null;
        cultivar: string;
        capture_at: string | null;
      }>();
  }

  async list(assessmentId: string) {
    const result = await this.db.prepare(`SELECT id, fruit_assessment_id, source, weight_g,
        confidence, model_name, model_version, source_ref, measured_at,
        created_by_member_id, created_at
      FROM fruit_weight_observations
      WHERE fruit_assessment_id = ?
      ORDER BY created_at ASC, id ASC`)
      .bind(assessmentId)
      .all<WeightObservationRow>();
    return result.results.map(mapRow);
  }

  async add(input: {
    fruitAssessmentId: string;
    source: WeightSource;
    weightG: number;
    confidence?: number | null;
    modelName?: string | null;
    modelVersion?: string | null;
    sourceRef?: string | null;
    measuredAt?: string | null;
    createdByMemberId?: string | null;
    createdAt?: string;
  }) {
    const id = crypto.randomUUID();
    const createdAt = input.createdAt ?? new Date().toISOString();
    await this.db.prepare(`INSERT INTO fruit_weight_observations(
        id, fruit_assessment_id, source, weight_g, confidence,
        model_name, model_version, source_ref, measured_at,
        created_by_member_id, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(
        id,
        input.fruitAssessmentId,
        input.source,
        input.weightG,
        input.confidence ?? null,
        input.modelName?.trim() || null,
        input.modelVersion?.trim() || null,
        input.sourceRef?.trim() || null,
        input.measuredAt?.trim() || null,
        input.createdByMemberId ?? null,
        createdAt,
      )
      .run();
    return id;
  }
}
