export const scoutingStates = [
  'BASELINE', 'WATCH', 'FIELD_CHECK_REQUIRED', 'SUSPECTED', 'CONFIRMED',
  'POST_TREATMENT', 'MONITORING', 'RESOLVED',
] as const;
export type ScoutingState = (typeof scoutingStates)[number];

export const fieldEvidenceCodes = [
  'NO_VISIBLE_EVIDENCE',
  'LEAF_DAMAGE_OBSERVED',
  'WEBBING_OR_MITE_TRACE_SUSPECTED',
  'DIRECT_MITE_OR_EGG_CONFIRMED',
  'OTHER_PEST_LIKE_EVIDENCE',
  'DISEASE_LIKE_EVIDENCE',
  'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY',
  'INCONCLUSIVE',
] as const;
export type FieldEvidenceCode = (typeof fieldEvidenceCodes)[number];

export type AlertDecision = 'ISSUED' | 'SUPPRESSED' | 'ESCALATED' | 'RECHECK_REQUESTED';

export type ScoutingSignals = {
  hasMeaningfulAnomaly: boolean;
  matchesRecentKnownPattern: boolean;
  hasMeaningfulNewEvidence: boolean;
  worseningTrend: boolean;
  spatialSpread: boolean;
  previousFieldCheckFresh: boolean;
  postTreatmentRebound: boolean;
};

export type ScoutingPolicyInput = {
  currentState: ScoutingState;
  hasActiveCase: boolean;
  signals: ScoutingSignals;
};

export type ScoutingPolicyDecision = {
  alertDecision: AlertDecision;
  nextState: ScoutingState;
  alertReason: string;
  suppressionReason: string | null;
  shouldOpenCase: boolean;
};

/**
 * No numeric thresholds live here. Upstream calibration converts thermal/environment/
 * temporal features into semantic signals, and this policy only decides lifecycle behavior.
 */
export function decideScoutingAlert(input: ScoutingPolicyInput): ScoutingPolicyDecision {
  const { currentState, hasActiveCase, signals } = input;

  if (!signals.hasMeaningfulAnomaly) {
    return {
      alertDecision: 'SUPPRESSED',
      nextState: currentState === 'POST_TREATMENT' ? 'MONITORING' : currentState,
      alertReason: 'NO_MEANINGFUL_ANOMALY',
      suppressionReason: 'NO_MEANINGFUL_NEW_EVIDENCE',
      shouldOpenCase: false,
    };
  }

  if (signals.postTreatmentRebound) {
    return {
      alertDecision: 'ESCALATED',
      nextState: 'FIELD_CHECK_REQUIRED',
      alertReason: 'POST_TREATMENT_REBOUND',
      suppressionReason: null,
      shouldOpenCase: !hasActiveCase,
    };
  }

  if (signals.worseningTrend || signals.spatialSpread || signals.hasMeaningfulNewEvidence) {
    return {
      alertDecision: hasActiveCase ? 'RECHECK_REQUESTED' : 'ISSUED',
      nextState: 'FIELD_CHECK_REQUIRED',
      alertReason: signals.spatialSpread
        ? 'SPATIAL_SPREAD'
        : signals.worseningTrend
          ? 'WORSENING_TREND'
          : 'NEW_FIELD_EVIDENCE',
      suppressionReason: null,
      shouldOpenCase: !hasActiveCase,
    };
  }

  if (signals.matchesRecentKnownPattern && signals.previousFieldCheckFresh) {
    return {
      alertDecision: 'SUPPRESSED',
      nextState: currentState === 'BASELINE' ? 'WATCH' : currentState,
      alertReason: 'KNOWN_PATTERN_CONTINUES',
      suppressionReason: 'RECENT_FIELD_CHECK_STILL_FRESH',
      shouldOpenCase: false,
    };
  }

  if (signals.matchesRecentKnownPattern) {
    return {
      alertDecision: hasActiveCase ? 'RECHECK_REQUESTED' : 'ISSUED',
      nextState: 'FIELD_CHECK_REQUIRED',
      alertReason: 'STALE_PREVIOUS_CHECK',
      suppressionReason: null,
      shouldOpenCase: !hasActiveCase,
    };
  }

  return {
    alertDecision: hasActiveCase ? 'RECHECK_REQUESTED' : 'ISSUED',
    nextState: 'FIELD_CHECK_REQUIRED',
    alertReason: hasActiveCase ? 'STALE_OR_CHANGED_PATTERN' : 'NEW_ANOMALY',
    suppressionReason: null,
    shouldOpenCase: !hasActiveCase,
  };
}

export function stateAfterFieldEvidence(evidence: FieldEvidenceCode): ScoutingState {
  switch (evidence) {
    case 'DIRECT_MITE_OR_EGG_CONFIRMED': return 'CONFIRMED';
    case 'WEBBING_OR_MITE_TRACE_SUSPECTED':
    case 'LEAF_DAMAGE_OBSERVED':
    case 'OTHER_PEST_LIKE_EVIDENCE':
    case 'DISEASE_LIKE_EVIDENCE':
    case 'PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY': return 'SUSPECTED';
    case 'NO_VISIBLE_EVIDENCE':
    case 'INCONCLUSIVE': return 'WATCH';
  }
}

export function stateAfterAction(actionCode: string): ScoutingState {
  return ['TREATMENT_APPLIED', 'LEAF_REMOVED', 'BIOCONTROL_APPLIED'].includes(actionCode)
    ? 'POST_TREATMENT'
    : 'MONITORING';
}
