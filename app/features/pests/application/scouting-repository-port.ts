import type { AlertDecision, FieldEvidenceCode, ScoutingState } from '../domain/scouting-policy';

export type ScoutingLocationStateRow = {
  id: string;
  farm_id: string;
  house_id: string;
  bed_id: string;
  zone_id: string;
  location_key: string;
  house_code: string;
  bed_code: string;
  zone_code: string;
  current_state: ScoutingState;
  active_case_id: string | null;
  last_observed_at: string | null;
  last_field_check_at: string | null;
  last_action_at: string | null;
  last_alert_at: string | null;
  last_alert_reason: string | null;
  recent_pattern_fingerprint: string | null;
  state_version: number;
};

export type ScoutingCaseRow = {
  id: string;
  farm_id: string;
  location_state_id: string;
  issue_family: 'PEST' | 'DISEASE' | 'PHYSIOLOGICAL_ENVIRONMENTAL' | 'UNKNOWN';
  primary_issue_code: string | null;
  status: 'OPEN' | 'MONITORING' | 'POST_TREATMENT' | 'RESOLVED';
  opened_at: string;
  closed_at?: string | null;
  close_reason?: string | null;
};

export type ScoutingPolicyProfile = {
  policy_version: string;
  freshness_mode: 'CALIBRATION_PENDING' | 'FIXED_WINDOW';
  field_check_freshness_minutes: number | null;
};

export type ObservationInput = {
  id: string;
  farmId: string;
  locationStateId: string;
  caseId: string | null;
  captureSessionId?: string | null;
  frameId?: string | null;
  sourceAssetId?: string | null;
  observedAt: string;
  sourceType: 'THERMAL' | 'RGB_REFERENCE' | 'SENSOR' | 'MANUAL' | 'FUSION';
  leafTemp?: number | null;
  ambientTemp?: number | null;
  referenceTemp?: number | null;
  humidity?: number | null;
  lightLevel?: number | null;
  thermalFeaturesJson?: string;
  rgbReferenceJson?: string;
  modelName?: string | null;
  modelVersion?: string | null;
  riskSignal?: number | null;
  noveltySignal?: number | null;
  trendSignal?: number | null;
  spatialSignal?: number | null;
  patternFingerprint?: string | null;
  policyInputJson: string;
};

export type OpenScoutingCaseInput = {
  farmId: string; locationStateId: string; issueFamily: ScoutingCaseRow['issue_family'];
  issueCode?: string | null; openedReason: string; now: string; previousCaseId?: string | null;
};

export type ValidateScoutingObservationScopeInput = {
  farmId: string; location: ScoutingLocationStateRow; captureSessionId?: string | null; frameId?: string | null;
};

export type AppendScoutingAlertInput = {
  id: string; farmId: string; locationStateId: string; caseId: string | null; observationId: string;
  decision: AlertDecision; reason: string; suppressionReason: string | null; policyVersion: string; now: string;
};

export type UpdateScoutingLocationInput = {
  locationStateId: string; nextState: ScoutingState; activeCaseId: string | null;
  observedAt: string; fingerprint?: string | null; alertAt?: string | null; alertReason?: string | null;
};

export type AppendScoutingFieldCheckInput = {
  id: string; farmId: string; locationStateId: string; caseId: string | null; observationId?: string | null;
  checkedAt: string; checkerMemberId: string; evidenceCode: FieldEvidenceCode;
  secondaryEvidenceJson?: string; note?: string | null;
};

export type ApplyScoutingFieldCheckStateInput = {
  locationStateId: string; caseId: string | null; nextState: ScoutingState;
  evidenceCode: FieldEvidenceCode; issueFamily?: ScoutingCaseRow['issue_family']; issueCode?: string | null; now: string;
};

export type AppendScoutingFieldCheckCorrectionInput = {
  id: string; farmId: string; fieldCheckId: string; locationStateId: string; caseId: string | null;
  correctionKind: 'REPLACE' | 'VOID'; replacementEvidenceCode?: FieldEvidenceCode | null;
  reasonCode: 'MISCLICK' | 'WRONG_OBSERVATION' | 'DUPLICATE' | 'OTHER'; note?: string | null;
  actorMemberId: string; now: string; nextState: ScoutingState;
  issueFamily?: ScoutingCaseRow['issue_family']; issueCode?: string | null;
};

export type AppendScoutingActionInput = {
  id: string; farmId: string; locationStateId: string; caseId: string | null;
  actionAt: string; actionCode: string; actorMemberId: string; detailJson?: string; note?: string | null;
  nextState: ScoutingState;
};

export type ResolveScoutingCaseInput = {
  farmId: string; locationStateId: string; caseId: string; reasonCode: string; actorMemberId: string; now: string;
};

export type CreateScoutingNotificationsInput = {
  farmId: string; locationState: ScoutingLocationStateRow; observationId: string;
  decision: Exclude<AlertDecision, 'SUPPRESSED'>; reason: string; now: string;
};

export type ScoutingFieldCheckRow = {
  id: string; farm_id: string; location_state_id: string; case_id: string | null;
  primary_evidence_code: FieldEvidenceCode; checked_at: string;
};

export interface ScoutingRepositoryPort {
  resolveLocation(farmId: string, houseId: string, bedId: string, zoneId: string, now: string): Promise<ScoutingLocationStateRow>;
  validateObservationScope(input: ValidateScoutingObservationScopeInput): Promise<string | null>;
  activeCase(locationStateId: string): Promise<ScoutingCaseRow | null>;
  latestResolvedCase(locationStateId: string): Promise<ScoutingCaseRow | null>;
  activePolicyProfile(): Promise<ScoutingPolicyProfile | null>;
  openCase(input: OpenScoutingCaseInput): Promise<string>;
  appendObservation(input: ObservationInput): Promise<void>;
  appendAlert(input: AppendScoutingAlertInput): Promise<void>;
  updateLocation(input: UpdateScoutingLocationInput): Promise<void>;
  createNotifications(input: CreateScoutingNotificationsInput): Promise<string[]>;
  locationHistory(farmId: string, locationStateId: string, limit?: number): Promise<{ location: ScoutingLocationStateRow } | null>;
  fieldCheckForCorrection(farmId: string, fieldCheckId: string): Promise<ScoutingFieldCheckRow | null>;
  appendFieldCheck(input: AppendScoutingFieldCheckInput): Promise<void>;
  applyFieldCheckState(input: ApplyScoutingFieldCheckStateInput): Promise<void>;
  appendFieldCheckCorrection(input: AppendScoutingFieldCheckCorrectionInput): Promise<void>;
  appendAction(input: AppendScoutingActionInput): Promise<void>;
  resolveCase(input: ResolveScoutingCaseInput): Promise<void>;
}
