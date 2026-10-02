import {
  describeResolvedWeight,
  type WeightObservation,
  type WeightSource,
  validateWeightObservation,
} from '../domain/weight-source';
import type { WeightObservationRepository } from '../infrastructure/weight-observation-repository';

export async function loadResolvedWeight(
  repository: WeightObservationRepository,
  farmId: string,
  assessmentId: string,
) {
  const assessment = await repository.assessment(farmId, assessmentId);
  if (!assessment) return null;
  const observations = await repository.list(assessmentId);
  return {
    assessment,
    observations,
    resolved: describeResolvedWeight(observations),
  };
}

export async function appendWeightObservation(
  repository: WeightObservationRepository,
  input: {
    farmId: string;
    fruitAssessmentId: string;
    source: WeightSource;
    weightG: number;
    confidence?: number | null;
    modelName?: string | null;
    modelVersion?: string | null;
    sourceRef?: string | null;
    measuredAt?: string | null;
    createdByMemberId?: string | null;
  },
) {
  const assessment = await repository.assessment(input.farmId, input.fruitAssessmentId);
  if (!assessment) return null;

  validateWeightObservation({
    source: input.source,
    weightG: input.weightG,
    confidence: input.confidence,
    modelName: input.modelName,
    modelVersion: input.modelVersion,
  });

  const id = await repository.add(input);
  const observations = await repository.list(input.fruitAssessmentId);
  return {
    id,
    assessment,
    observations,
    resolved: describeResolvedWeight(observations),
  };
}

export async function appendManualMeasuredWeight(
  repository: WeightObservationRepository,
  input: {
    farmId: string;
    fruitAssessmentId: string;
    weightG: number;
    measuredAt?: string | null;
    createdByMemberId?: string | null;
  },
) {
  return appendWeightObservation(repository, {
    ...input,
    source: 'MANUAL_MEASURED',
  });
}

export async function appendSensorMeasuredWeight(
  repository: WeightObservationRepository,
  input: {
    farmId: string;
    fruitAssessmentId: string;
    weightG: number;
    sourceRef?: string | null;
    measuredAt?: string | null;
  },
) {
  return appendWeightObservation(repository, {
    ...input,
    source: 'SENSOR_MEASURED',
  });
}

export async function appendVisionEstimatedWeight(
  repository: WeightObservationRepository,
  input: {
    farmId: string;
    fruitAssessmentId: string;
    weightG: number;
    confidence?: number | null;
    modelName: string;
    modelVersion: string;
    sourceRef?: string | null;
  },
) {
  return appendWeightObservation(repository, {
    ...input,
    source: 'VISION_ESTIMATED',
  });
}

export function publicWeightObservation(row: WeightObservation) {
  return {
    id: row.id,
    source: row.source,
    weightG: row.weightG,
    confidence: row.confidence,
    modelName: row.modelName,
    modelVersion: row.modelVersion,
    measuredAt: row.measuredAt,
    createdAt: row.createdAt,
  };
}
