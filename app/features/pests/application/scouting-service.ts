import {
  decideScoutingAlert,
  fieldEvidenceCodes,
  stateAfterAction,
  stateAfterFieldEvidence,
  type FieldEvidenceCode,
  type ScoutingSignals,
  type ScoutingState,
} from '../domain/scouting-policy';
import {
  ScoutingRepository,
  type ScoutingCaseRow,
  type ScoutingPolicyProfile,
} from '../infrastructure/scouting-repository';

export const SCOUTING_POLICY_VERSION = 'PEST-SCOUT-V2-20260916';

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

function resolveFieldCheckFreshness(input: {
  profile: ScoutingPolicyProfile | null;
  lastFieldCheckAt: string | null;
  observedAt: string;
  upstreamFresh: boolean;
}) {
  const minutes = input.profile?.field_check_freshness_minutes;
  if (input.profile?.freshness_mode === 'FIXED_WINDOW' && typeof minutes === 'number' && input.lastFieldCheckAt) {
    const elapsedMs = new Date(input.observedAt).getTime() - new Date(input.lastFieldCheckAt).getTime();
    const validTime = Number.isFinite(elapsedMs) && elapsedMs >= 0;
    return {
      fresh: validTime && elapsedMs <= minutes * 60_000,
      source: 'VERSIONED_FIXED_WINDOW',
    } as const;
  }
  return {
    fresh: input.upstreamFresh,
    source: 'UPSTREAM_SEMANTIC',
  } as const;
}

export async function processScoutingObservation(repository: ScoutingRepository, input: ProcessScoutingObservationInput) {
  const location = await repository.resolveLocation(input.farmId, input.houseId, input.bedId, input.zoneId, input.observedAt);
  const normalizedSessionId = await repository.validateObservationScope({
    farmId: input.farmId,
    location,
    captureSessionId: input.captureSessionId,
    frameId: input.frameId,
  });
  let activeCase = await repository.activeCase(location.id);
  const policyProfile = await repository.activePolicyProfile();
  const freshness = resolveFieldCheckFreshness({
    profile: policyProfile,
    lastFieldCheckAt: location.last_field_check_at,
    observedAt: input.observedAt,
    upstreamFresh: input.signals.previousFieldCheckFresh,
  });
  const exactKnownPattern = Boolean(
    input.patternFingerprint
    && location.recent_pattern_fingerprint
    && input.patternFingerprint === location.recent_pattern_fingerprint,
  );
  const effectiveSignals: ScoutingSignals = {
    ...input.signals,
    matchesRecentKnownPattern: input.signals.matchesRecentKnownPattern || exactKnownPattern,
    previousFieldCheckFresh: freshness.fresh,
  };
  const decision = decideScoutingAlert({
    currentState: location.current_state as ScoutingState,
    hasActiveCase: Boolean(activeCase),
    signals: effectiveSignals,
  });

  if (decision.shouldOpenCase && !activeCase) {
    const previousResolved = await repository.latestResolvedCase(location.id);
    const caseId = await repository.openCase({
      farmId: input.farmId,
      locationStateId: location.id,
      issueFamily: input.issueFamily ?? 'UNKNOWN',
      issueCode: input.issueCode ?? null,
      openedReason: decision.alertReason,
      now: input.observedAt,
      previousCaseId: previousResolved?.id ?? null,
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
    captureSessionId: normalizedSessionId,
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
    policyInputJson: safeJson({
      signals: effectiveSignals,
      policyVersion: policyProfile?.policy_version ?? SCOUTING_POLICY_VERSION,
      freshnessSource: freshness.source,
      configuredFreshnessMinutes: policyProfile?.field_check_freshness_minutes ?? null,
    }),
  });

  const appliedPolicyVersion = policyProfile?.policy_version ?? SCOUTING_POLICY_VERSION;
  await repository.appendAlert({
    id: crypto.randomUUID(),
    farmId: input.farmId,
    locationStateId: location.id,
    caseId: activeCase?.id ?? null,
    observationId,
    decision: decision.alertDecision,
    reason: decision.alertReason,
    suppressionReason: decision.suppressionReason,
    policyVersion: appliedPolicyVersion,
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
    policyVersion: appliedPolicyVersion,
    freshnessSource: freshness.source,
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
  const fieldCheckId = crypto.randomUUID();

  await repository.appendFieldCheck({
    id: fieldCheckId,
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
    fieldCheckId,
    locationStateId: input.locationStateId,
    caseId: activeCase?.id ?? null,
    evidenceCode,
    nextState,
    definitiveNegative: false,
  };
}

export async function correctScoutingFieldCheck(repository: ScoutingRepository, input: {
  farmId: string;
  fieldCheckId: string;
  memberId: string;
  correctionKind: 'REPLACE' | 'VOID';
  replacementEvidenceCode?: string | null;
  reasonCode: 'MISCLICK' | 'WRONG_OBSERVATION' | 'DUPLICATE' | 'OTHER';
  correctedAt: string;
  note?: string | null;
}) {
  const original = await repository.fieldCheckForCorrection(input.farmId, input.fieldCheckId);
  if (!original) throw new Error('수정할 현장 점검 기록을 찾을 수 없습니다.');

  let replacement: FieldEvidenceCode | null = null;
  if (input.correctionKind === 'REPLACE') {
    if (!fieldEvidenceCodes.includes(input.replacementEvidenceCode as FieldEvidenceCode)) {
      throw new Error('수정할 현장 점검 결과를 다시 선택해 주세요.');
    }
    replacement = input.replacementEvidenceCode as FieldEvidenceCode;
  }
  const nextState: ScoutingState = replacement ? stateAfterFieldEvidence(replacement) : 'WATCH';
  const classification = replacement ? caseClassificationFromEvidence(replacement) : {};
  const correctionId = crypto.randomUUID();
  await repository.appendFieldCheckCorrection({
    id: correctionId,
    farmId: input.farmId,
    fieldCheckId: original.id,
    locationStateId: original.location_state_id,
    caseId: original.case_id,
    correctionKind: input.correctionKind,
    replacementEvidenceCode: replacement,
    reasonCode: input.reasonCode,
    note: input.note,
    actorMemberId: input.memberId,
    now: input.correctedAt,
    nextState,
    issueFamily: classification.issueFamily,
    issueCode: classification.issueCode,
  });
  return {
    correctionId,
    fieldCheckId: original.id,
    locationStateId: original.location_state_id,
    correctionKind: input.correctionKind,
    replacementEvidenceCode: replacement,
    nextState,
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

export async function resolveScoutingCase(repository: ScoutingRepository, input: {
  farmId: string;
  locationStateId: string;
  memberId: string;
  reasonCode: string;
  resolvedAt: string;
}) {
  const allowedReasons = new Set(['NO_FURTHER_ABNORMALITY', 'TREATMENT_COMPLETED', 'FALSE_ALARM_CLOSED', 'OTHER']);
  if (!allowedReasons.has(input.reasonCode)) throw new Error('종료 사유를 다시 선택해 주세요.');
  const history = await repository.locationHistory(input.farmId, input.locationStateId, 1);
  if (!history) throw new Error('이 농장의 예찰 구역을 찾을 수 없습니다.');
  const activeCase = await repository.activeCase(input.locationStateId);
  if (!activeCase) throw new Error('종료할 진행 중 예찰 건이 없습니다.');
  await repository.resolveCase({
    farmId: input.farmId,
    locationStateId: input.locationStateId,
    caseId: activeCase.id,
    reasonCode: input.reasonCode,
    actorMemberId: input.memberId,
    now: input.resolvedAt,
  });
  return { locationStateId: input.locationStateId, caseId: activeCase.id, state: 'RESOLVED' as const };
}
