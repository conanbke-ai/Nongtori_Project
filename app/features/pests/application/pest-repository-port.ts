export type PestAlertRow = {
  id: string;
  pest_code: string;
  item_id: string | null;
  item_name: string | null;
  crop_name: string | null;
  cultivar_name: string | null;
  class_label: string;
  confidence: number | null;
  decision_status: string;
  created_at: string;
  house_name: string | null;
  bed_name: string | null;
  zone_name: string | null;
  review_verdict: string | null;
  review_quick_note_code: string | null;
  review_note: string | null;
  review_note_language: string | null;
  reviewer_member_id: string | null;
  reviewer_name: string | null;
  reviewer_role: string | null;
  reviewed_at: string | null;
};

export type PestCountRow = {
  pest_code: string;
  review_status: string;
  count: number;
};

export type PestReviewTarget = {
  id: string;
  pest_code: string;
  inference_run_id: string;
  track_id: string | null;
};

export type PestReviewInput = {
  farmId: string;
  predictionId: string;
  memberId: string;
  name: string;
  role: string;
  verdict: string;
  quickNote: string;
  note: string;
  language: string;
  now: string;
};

export interface PestRepositoryPort {
  counts(farmId: string): Promise<PestCountRow[]>;
  list(farmId: string, code: string, status: string, limit: number, offset: number): Promise<PestAlertRow[]>;
  target(farmId: string, predictionId: string): Promise<PestReviewTarget | null>;
  addReview(input: PestReviewInput): Promise<unknown>;
}
