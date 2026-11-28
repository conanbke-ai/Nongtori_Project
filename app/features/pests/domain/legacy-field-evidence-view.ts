import type { FieldEvidenceCode } from './scouting-policy';

export type LegacyFindingFamily = 'PEST' | 'DISEASE' | 'PHYSIOLOGICAL_ENVIRONMENTAL' | 'UNKNOWN' | 'NONE_VISIBLE';
export type DerivedLegacyFinding = Readonly<{
  family: LegacyFindingFamily;
  issueCode: 'SPIDER_MITE' | null;
  certainty: null;
  severity: null;
}>;
export type LegacyFieldEvidenceView = Readonly<{
  source: Readonly<{ kind: 'LEGACY_CODE_INPUT'; code: string | null }>;
  derived: Readonly<{
    kind: 'DERIVED_LEGACY_READING';
    mapperVersion: 'LEGACY_FIELD_EVIDENCE_V1';
    status: 'RECOGNIZED' | 'UNKNOWN_CODE' | 'INVALID_INPUT';
    findings: readonly DerivedLegacyFinding[];
    definitiveNegative: false;
  }>;
}>;

// Observation categories only, not CASE classifications or validated diagnoses.
// Symptoms/uncertainty do not manufacture a species or a certainty score.
const interpretations = {
  NO_VISIBLE_EVIDENCE: { family: 'NONE_VISIBLE', issueCode: null },
  LEAF_DAMAGE_OBSERVED: { family: 'UNKNOWN', issueCode: null },
  WEBBING_OR_MITE_TRACE_SUSPECTED: { family: 'UNKNOWN', issueCode: null },
  DIRECT_MITE_OR_EGG_CONFIRMED: { family: 'PEST', issueCode: 'SPIDER_MITE' },
  OTHER_PEST_LIKE_EVIDENCE: { family: 'PEST', issueCode: null },
  DISEASE_LIKE_EVIDENCE: { family: 'DISEASE', issueCode: null },
  PHYSIOLOGICAL_OR_ENVIRONMENTAL_ABNORMALITY: { family: 'PHYSIOLOGICAL_ENVIRONMENTAL', issueCode: null },
  INCONCLUSIVE: { family: 'UNKNOWN', issueCode: null },
} as const satisfies Record<FieldEvidenceCode, { family: LegacyFindingFamily; issueCode: 'SPIDER_MITE' | null }>;

// Deliberately ignores secondaryEvidence and all identity/location/note metadata.
// This pure view cannot authorize, persist or update state; consumers are read only.
export function readLegacyFieldEvidence(input: Readonly<{
  primaryEvidenceCode: unknown; secondaryEvidence?: unknown;
}>): LegacyFieldEvidenceView {
  const value = input.primaryEvidenceCode;
  const code = typeof value === 'string' ? value : null;
  const recognized = code !== null && Object.hasOwn(interpretations, code);
  const interpretation = recognized ? interpretations[code as FieldEvidenceCode] : null;
  return {
    source: { kind: 'LEGACY_CODE_INPUT', code },
    derived: {
      kind: 'DERIVED_LEGACY_READING', mapperVersion: 'LEGACY_FIELD_EVIDENCE_V1',
      status: code === null ? 'INVALID_INPUT' : recognized ? 'RECOGNIZED' : 'UNKNOWN_CODE',
      findings: interpretation ? [{ ...interpretation, certainty: null, severity: null }] : [],
      definitiveNegative: false,
    },
  };
}
