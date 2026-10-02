export const weightSources = [
  'SENSOR_MEASURED',
  'MANUAL_MEASURED',
  'VISION_ESTIMATED',
] as const;

export type WeightSource = (typeof weightSources)[number];

export type WeightObservation = {
  id: string;
  fruitAssessmentId: string;
  source: WeightSource;
  weightG: number;
  confidence: number | null;
  modelName: string | null;
  modelVersion: string | null;
  sourceRef: string | null;
  measuredAt: string | null;
  createdByMemberId: string | null;
  createdAt: string;
};

export type WeightGrade =
  | 'SP_WEIGHT'
  | 'HI_WEIGHT'
  | 'MD_WEIGHT'
  | 'JM_WEIGHT_CANDIDATE';

const sourcePriority: Record<WeightSource, number> = {
  SENSOR_MEASURED: 3,
  MANUAL_MEASURED: 2,
  VISION_ESTIMATED: 1,
};

export function isWeightSource(value: unknown): value is WeightSource {
  return typeof value === 'string' && weightSources.includes(value as WeightSource);
}

export function weightGrade(weightG: number): WeightGrade {
  if (!Number.isFinite(weightG) || weightG <= 0) {
    throw new Error('weight_g must be a positive finite number');
  }
  if (weightG >= 22) return 'SP_WEIGHT';
  if (weightG >= 16) return 'HI_WEIGHT';
  if (weightG >= 12) return 'MD_WEIGHT';
  return 'JM_WEIGHT_CANDIDATE';
}

export function weightSourceRank(source: WeightSource) {
  return sourcePriority[source];
}

export function validateWeightObservation(input: {
  source: WeightSource;
  weightG: number;
  confidence?: number | null;
  modelName?: string | null;
  modelVersion?: string | null;
}) {
  if (!Number.isFinite(input.weightG) || input.weightG <= 0) {
    throw new Error('weight_g must be a positive finite number');
  }

  const confidence = input.confidence ?? null;
  if (
    confidence !== null
    && (!Number.isFinite(confidence) || confidence < 0 || confidence > 1)
  ) {
    throw new Error('confidence must be between 0 and 1');
  }

  const modelName = input.modelName?.trim() || null;
  const modelVersion = input.modelVersion?.trim() || null;

  if (input.source === 'VISION_ESTIMATED') {
    if (!modelName || !modelVersion) {
      throw new Error('VISION_ESTIMATED requires model_name and model_version');
    }
  } else if (modelName || modelVersion || confidence !== null) {
    throw new Error('Measured weight sources cannot carry model metadata or confidence');
  }
}

function observationTimestamp(row: WeightObservation) {
  const measured = row.measuredAt ? Date.parse(row.measuredAt) : Number.NaN;
  const created = Date.parse(row.createdAt);
  return Number.isFinite(measured)
    ? measured
    : Number.isFinite(created)
      ? created
      : 0;
}

export function resolvePreferredWeight(
  observations: readonly WeightObservation[],
): WeightObservation | null {
  if (!observations.length) return null;

  return [...observations].sort((left, right) => {
    const priority = weightSourceRank(right.source) - weightSourceRank(left.source);
    if (priority !== 0) return priority;

    const time = observationTimestamp(right) - observationTimestamp(left);
    if (time !== 0) return time;

    return right.id.localeCompare(left.id);
  })[0] ?? null;
}

export function describeResolvedWeight(observations: readonly WeightObservation[]) {
  const selected = resolvePreferredWeight(observations);
  return selected
    ? {
        observationId: selected.id,
        weightG: selected.weightG,
        source: selected.source,
        provisionalWeightGrade: weightGrade(selected.weightG),
        confidence: selected.confidence,
        modelName: selected.modelName,
        modelVersion: selected.modelVersion,
        measuredAt: selected.measuredAt,
      }
    : null;
}
