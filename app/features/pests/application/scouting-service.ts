import {
  decideScoutingAlert,
  fieldEvidenceCodes,
  stateAfterAction,
  stateAfterFieldEvidence,
  type FieldEvidenceCode,
  type ScoutingSignals,
  type ScoutingState,
} from '../domain/scouting-policy';
import { ScoutingRepository, type ScoutingCaseRow } from '../infrastructure/scouting-repository';

export const SCOUTING_POLICY_VERSION = 'PEST-SCOUT-V1-20260916';

export type ProcessScoutingObservationInput = {
  farmId: string;
  houseId: string;
  bedId: string;
  zoneId: string;
  observedAt: string;
  sourceType: 'THERMAL' | 'RGB_REFERENCE' | 'SENSOR' | 'MANUAL' | 'FUSION';
  issueFamily?: ScoutingCaseRow['issue_family'];
  issueCode?: string | null;
  signals: ScoutingSignals;
  captureSessionId?: string | null;
  frameId?: string | null;
  sourceAssetId?: string | null;
  leafTemp?: number | null;
  ambientTemp?: number | null;
  referenceTemp?: number | null;
  humidity?: number | null;
  lightLevel?: number | null;
  thermalFeatures?: unknown;
  rgbReference?: unknown;
  modelName?: string | null;
  modelVersion?: string | null;
  riskSignal?: number | null;
  noveltySignal?: number | null;
  trendSignal?: number | null;
  spatialSignal?: number | null;
  patternFingerprint?: string | null;
};

function safeJson(value: unknown) {
  try { return JSON.stringify(value ?? {}); } catch { return '{}'; }
}

function caseClassificationFromEvidence(evidence: FieldEvidenceCode): {
  issueFamily?: ScoutingCaseRow['issue_family'];
  issueCode?: string;
} {
  switch (evidence) {
    case 'DIRECT_MITE_OR_EGG_CONFIRMED': return { issueFamily: 'PEST', issueCode: 'SPIDER_MITE' };
    case 'OTHER_PEST_LIKE_EVIDENCE': return { issueFamily: 'PEST', issueCode: 'UNKNOWN_PEST' };
    case 'DISEASE_LIKE_EVIDENCE': return { issueFamily: 'DISEASE', issueCode: 'UNKNOWN_DISEASE' };
    case 'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY':
      return { issueFamily: 'PHYSIOLOGICAL_ENVIRONMENTAL', issueCode: 'ENVIRONMENTAL_STRESS' };
    default: return {};
  }
}

export async function processScoutingObservation(repository: ScoutingRepository, input: ProcessScoutingObservationInput) {
  const location = await repository.resolveLocation(input.farmId, input.houseId, input.bedId, input.zoneId, input.observedAt);
  let activeCase = await repository.activeCase(location.id);
  const exactKnownPattern = Boolean(
    input.patternFingerprint
    && location.recent_pattern_fingerprint
    && input.patternFingerprint === location.recent_pattern_fingerprint,
  );
  const effectiveSignals: ScoutingSignals = {
    ...input.signals,
    matchesRecentKnownPattern: input.signals.matchesRecentKnownPattern || exactKnownPattern,
  };
  const decision = decideScoutingAlert({
    currentState: location.current_state as ScoutingState,
    hasActiveCase: Boolean(activeCase),
    signals: effectiveSignals,
  });

  if (decision.shouldOpenCase && !activeCase) {
    const caseId = await repository.openCase({
      farmId: input.farmId,
      locationStateId: location.id,
      issueFamily: input.issueFamily ?? 'UNKNOWN',
      issueCode: input.issueCode ?? null,
      openedReason: decision.alertReason,
      now: input.observedAt,
    });
    activeCase = {
      id: caseId,
      farm_id: input.farmId,
      location_state_id: location.id,
      issue_family: input.issueFamily ?? 'UNKNOWN',
      primary_issue_code: input.issueCode ?? null,
      status: 'OPEN',
      opened_at: input.observedAt,
    };
  }

  const observationId = crypto.randomUUID();
  await repository.appendObservation({
    id: observationId,
    farmId: input.farmId,
    locationStateId: location.id,
    caseId: activeCase?.id ?? null,
    captureSessionId: input.captureSessionId,
    frameId: input.frameId,
    sourceAssetId: input.sourceAssetId,
    observedAt: input.observedAt,
    sourceType: input.sourceType,
    leafTemp: input.leafTemp,
    ambientTemp: input.ambientTemp,
    referenceTemp: input.referenceTemp,
    humidity: input.humidity,
    lightLevel: input.lightLevel,
    thermalFeaturesJson: safeJson(input.thermalFeatures),
    rgbReferenceJson: safeJson(input.rgbReference),
    modelName: input.modelName,
    modelVersion: input.modelVersion,
    riskSignal: input.riskSignal,
    noveltySignal: input.noveltySignal,
    trendSignal: input.trendSignal,
    spatialSignal: input.spatialSignal,
    patternFingerprint: input.patternFingerprint,
    policyInputJson: safeJson(effectiveSignals),
  });

  await repository.appendAlert({
    id: crypto.randomUUID(),
    farmId: input.farmId,
    locationStateId: location.id,
    caseId: activeCase?.id ?? null,
    observationId,
    decision: decision.alertDecision,
    reason: decision.alertReason,
    suppressionReason: decision.suppressionReason,
    policyVersion: SCOUTING_POLICY_VERSION,
    now: input.observedAt,
  });

  const alertIssued = decision.alertDecision !== 'SUPPRESSED';
  await repository.updateLocation({
    locationStateId: location.id,
    nextState: decision.nextState,
    activeCaseId: activeCase?.id ?? null,
    observedAt: input.observedAt,
    fingerprint: input.patternFingerprint,
    alertAt: alertIssued ? input.observedAt : null,
    alertReason: alertIssued ? decision.alertReason : null,
  });

  let notificationIds: string[] = [];
  if (decision.alertDecision !== 'SUPPRESSED') {
    notificationIds = await repository.createNotifications({
      farmId: input.farmId,
      locationState: location,
      observationId,
      decision: decision.alertDecision,
      reason: decision.alertReason,
      now: input.observedAt,
    });
  }

  return {
    observationId,
    locationStateId: location.id,
    caseId: activeCase?.id ?? null,
    alertDecision: decision.alertDecision,
    alertReason: decision.alertReason,
    suppressionReason: decision.suppressionReason,
    nextState: decision.nextState,
    notificationCount: notificationIds.length,
  };
}

export async function recordScoutingFieldCheck(repository: ScoutingRepository, input: {
  farmId: string;
  locationStateId: string;
  memberId: string;
  evidenceCode: string;
  checkedAt: string;
  observationId?: string | null;
  note?: string | null;
  secondaryEvidence?: unknown;
}) {
  if (!fieldEvidenceCodes.includes(input.evidenceCode as FieldEvidenceCode)) {
    throw new Error('현장 점검 결과를 다시 선택해 주세요.');
  }
  const evidenceCode = input.evidenceCode as FieldEvidenceCode;
  const history = await repository.locationHistory(input.farmId, input.locationStateId, 1);
  if (!history) throw new Error('이 농장의 예찰 구역을 찾을 수 없습니다.');
  const activeCase = await repository.activeCase(input.locationStateId);
  const nextState = stateAfterFieldEvidence(evidenceCode);
  const classification = caseClassificationFromEvidence(evidenceCode);

  await repository.appendFieldCheck({
    id: crypto.randomUUID(),
    farmId: input.farmId,
    locationStateId: input.locationStateId,
    caseId: activeCase?.id ?? null,
    observationId: input.observationId ?? null,
    checkedAt: input.checkedAt,
    checkerMemberId: input.memberId,
    evidenceCode,
    secondaryEvidenceJson: safeJson(input.secondaryEvidence),
    note: input.note ?? null,
  });
  await repository.applyFieldCheckState({
    locationStateId: input.locationStateId,
    caseId: activeCase?.id ?? null,
    nextState,
    evidenceCode,
    issueFamily: classification.issueFamily,
    issueCode: classification.issueCode,
    now: input.checkedAt,
  });

  return {
    locationStateId: input.locationStateId,
    caseId: activeCase?.id ?? null,
    evidenceCode,
    nextState,
    definitiveNegative: false,
  };
}

export async function recordScoutingAction(repository: ScoutingRepository, input: {
  farmId: string;
  locationStateId: string;
  memberId: string;
  actionCode: string;
  actionAt: string;
  detail?: unknown;
  note?: string | null;
}) {
  const allowed = new Set(['TREATMENT_APPLIED', 'LEAF_REMOVED', 'BIOCONTROL_APPLIED', 'OBSERVE_ONLY', 'OTHER_ACTION']);
  if (!allowed.has(input.actionCode)) throw new Error('현장 조치를 다시 선택해 주세요.');
  const history = await repository.locationHistory(input.farmId, input.locationStateId, 1);
  if (!history) throw new Error('이 농장의 예찰 구역을 찾을 수 없습니다.');
  const activeCase = await repository.activeCase(input.locationStateId);
  const nextState = stateAfterAction(input.actionCode);
  await repository.appendAction({
    id: crypto.randomUUID(),
    farmId: input.farmId,
    locationStateId: input.locationStateId,
    caseId: activeCase?.id ?? null,
    actionAt: input.actionAt,
    actionCode: input.actionCode,
    actorMemberId: input.memberId,
    detailJson: safeJson(input.detail),
    note: input.note ?? null,
    nextState,
  });
  return { locationStateId: input.locationStateId, caseId: activeCase?.id ?? null, actionCode: input.actionCode, nextState };
}
