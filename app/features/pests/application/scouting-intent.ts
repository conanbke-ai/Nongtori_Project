import { ScoutingRepository } from '../infrastructure/scouting-repository';
import { ScoutingReceiptRepository, type ReceiptRow } from '../infrastructure/scouting-receipt-repository';
import { correctScoutingFieldCheck, recordScoutingAction, recordScoutingFieldCheck, resolveScoutingCase, ScoutingMutationValidationError } from './scouting-service';

export type ScoutingMutationKind = 'CHECK' | 'CORRECTION' | 'ACTION' | 'RESOLVE';
export class ScoutingIntentError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) { super(message); }
}
export function stableIntentJson(value: unknown): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableIntentJson).join(',')}]`;
  if (typeof value === 'object' && value) return `{${Object.keys(value).sort().map(key =>
    `${JSON.stringify(key)}:${stableIntentJson((value as Record<string, unknown>)[key])}`).join(',')}}`;
  throw new ScoutingIntentError(422, 'INVALID_INTENT', '지원하지 않는 입력입니다.');
}
export async function intentDigest(value: string) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))]
    .map(byte => byte.toString(16).padStart(2, '0')).join('');
}
export function normalizeScoutingIntent(operation: ScoutingMutationKind, body: Record<string, unknown>) {
  const fail = () => { throw new ScoutingIntentError(422, 'INVALID_INTENT', '입력 내용을 확인해 주세요.'); };
  const text = (key: string, max: number) => {
    const v = typeof body[key] === 'string' ? body[key].trim() : '';
    if (v.length > max) fail(); return v;
  };
  const names = {
    CHECK: ['locationStateId','evidenceCode','observationId','secondaryEvidence','checkedAt'],
    CORRECTION: ['fieldCheckId','correctionKind','replacementEvidenceCode','reasonCode','correctedAt'],
    ACTION: ['locationStateId','actionCode','detail','actionAt'],
    RESOLVE: ['locationStateId','reasonCode','resolvedAt'],
  };
  if (Object.keys(body).some(key => !['farmId','note',...names[operation]].includes(key))) fail();
  const farmId = text('farmId', 100);
  const targetId = text(operation === 'CORRECTION' ? 'fieldCheckId' : 'locationStateId', 100);
  if (!farmId || !targetId) fail();
  const fields: Record<string, unknown> = { farmId, targetId, note: text('note', 300) || null };
  const timeKey = { CHECK: 'checkedAt', CORRECTION: 'correctedAt', ACTION: 'actionAt', RESOLVE: 'resolvedAt' }[operation];
  fields[timeKey] = text(timeKey, 40) || null; // omission marker, not today's clock
  if (operation === 'CHECK') Object.assign(fields, { evidenceCode: text('evidenceCode',80),
    observationId: text('observationId',100) || null, secondaryEvidence: body.secondaryEvidence ?? null });
  if (operation === 'CORRECTION') Object.assign(fields, { correctionKind: text('correctionKind',20),
    replacementEvidenceCode: text('replacementEvidenceCode',80) || null, reasonCode: text('reasonCode',40) || 'MISCLICK' });
  if (operation === 'ACTION') Object.assign(fields, { actionCode: text('actionCode',80), detail: body.detail ?? null });
  if (operation === 'RESOLVE') fields.reasonCode = text('reasonCode',60);
  if (operation === 'CORRECTION' && !['REPLACE','VOID'].includes(fields.correctionKind as string)) fail();
  return { farmId, targetId, operation, fields };
}
export type NormalizedScoutingIntent = ReturnType<typeof normalizeScoutingIntent>;
function replay(row: ReceiptRow, hash: string) {
  if (row.canonical_version !== 1) throw new ScoutingIntentError(409, 'REPLAY_VERSION_UNSUPPORTED', '이 요청의 처리 결과를 확인해 주세요.');
  if (row.payload_hash !== hash) throw new ScoutingIntentError(409, 'INTENT_CONFLICT', '같은 요청 키로 입력을 바꿀 수 없습니다.');
  return { status: row.http_status, body: JSON.parse(row.response_json) as Record<string, unknown> };
}
// Read only: no mutation plan, no receipt creation, quota consumption or bootstrap.
export async function lookupScoutingIntent(db: D1Database, memberId: string, key: string,
  intent: NormalizedScoutingIntent) {
  const receipts = new ScoutingReceiptRepository(db);
  if (!await receipts.schemaAvailable()) throw new ScoutingIntentError(503, 'RECEIPT_SCHEMA_UNAVAILABLE', '요청 기록 기능이 준비되지 않았습니다.');
  if (!await receipts.ownsTarget(intent.farmId, intent.operation, intent.targetId))
    throw new ScoutingIntentError(400, 'TARGET_NOT_FOUND', '이 농장의 기록을 찾을 수 없습니다.');
  const scope = { farmId: intent.farmId, memberId, operation: intent.operation, keyDigest: await intentDigest(key) };
  const row = await receipts.find(scope);
  if (!row) return { state: 'UNCONFIRMED' as const };
  const result = replay(row, await intentDigest(stableIntentJson(intent.fields)));
  return { state: 'COMMITTED' as const, originalStatus: result.status, result: result.body };
}
export async function executeScoutingIntent(db: D1Database, memberId: string, key: string,
  intent: NormalizedScoutingIntent, limits: { farm: number; member: number }) {
  const receipts = new ScoutingReceiptRepository(db);
  if (!await receipts.schemaAvailable()) throw new ScoutingIntentError(503, 'RECEIPT_SCHEMA_UNAVAILABLE', '요청 기록 기능이 준비되지 않았습니다.');
  if (!await receipts.ownsTarget(intent.farmId, intent.operation, intent.targetId))
    throw new ScoutingIntentError(400, 'TARGET_NOT_FOUND', '이 농장의 기록을 찾을 수 없습니다.');
  const scope = { farmId: intent.farmId, memberId, operation: intent.operation, keyDigest: await intentDigest(key) };
  const hash = await intentDigest(stableIntentJson(intent.fields));
  const previous = await receipts.find(scope);
  if (previous) return replay(previous, hash);
  const plan: D1PreparedStatement[] = [];
  const repo = new ScoutingRepository(db, plan), p = intent.fields;
  const shared = { farmId: intent.farmId, memberId, note: p.note as string | null };
  const stamp = new Date().toISOString();
  let result: Record<string, unknown>;
  // Reuse existing domain behavior, including historical correction semantics.
  // No new expected-case/version precondition or new audit event is introduced.
  try {
    if (intent.operation === 'CHECK') result = { ...await recordScoutingFieldCheck(repo, { ...shared,
      locationStateId: intent.targetId, evidenceCode: p.evidenceCode as string,
      observationId: p.observationId as string | null, secondaryEvidence: p.secondaryEvidence,
      checkedAt: p.checkedAt as string || stamp }), message: '현장 관찰 사실을 기록했습니다.' };
    else if (intent.operation === 'CORRECTION') result = { ...await correctScoutingFieldCheck(repo, { ...shared,
      fieldCheckId: intent.targetId, correctionKind: p.correctionKind as 'REPLACE' | 'VOID',
      replacementEvidenceCode: p.replacementEvidenceCode as string | null,
      reasonCode: p.reasonCode as 'MISCLICK' | 'WRONG_OBSERVATION' | 'DUPLICATE' | 'OTHER',
      correctedAt: p.correctedAt as string || stamp }), message: '현장 점검 입력을 수정 기록으로 남겼습니다.' };
    else if (intent.operation === 'ACTION') result = { ...await recordScoutingAction(repo, { ...shared,
      locationStateId: intent.targetId, actionCode: p.actionCode as string, detail: p.detail,
      actionAt: p.actionAt as string || stamp }), message: '현장 조치를 기록했습니다.' };
    else result = { ...await resolveScoutingCase(repo, { ...shared, locationStateId: intent.targetId,
      reasonCode: p.reasonCode as string, resolvedAt: p.resolvedAt as string || stamp }), message: '예찰 건을 종료했습니다.' };
  } catch (error) {
    // A concurrent resolve can remove the active case after our initial miss.
    const winner = await receipts.find(scope); if (winner) return replay(winner, hash);
    if (error instanceof ScoutingMutationValidationError)
      throw new ScoutingIntentError(400, 'INVALID_MUTATION', '입력 또는 현재 예찰 기록을 확인해 주세요.');
    throw new ScoutingIntentError(503, 'MUTATION_RESULT_UNCERTAIN', '저장 결과를 확인할 수 없습니다. 같은 요청 키를 유지해 주세요.');
  }
  const status = intent.operation === 'RESOLVE' ? 200 : 201, json = JSON.stringify(result);
  if (new TextEncoder().encode(json).byteLength > 4096)
    throw new ScoutingIntentError(422, 'RESPONSE_TOO_LARGE', '처리 결과를 기록할 수 없습니다.');
  try { await receipts.commit(scope, hash, { status, json }, plan, limits); }
  catch (error) {
    // Recover only an actually committed, scoped receipt; unknown errors stay uncertain.
    const winner = await receipts.find(scope); if (winner) return replay(winner, hash);
    if (error instanceof Error && error.message.includes('scouting_receipt_quota'))
      throw new ScoutingIntentError(429, 'RECEIPT_LIMIT', '새 요청 기록 한도에 도달했습니다. 기존 요청 결과를 확인해 주세요.');
    throw new ScoutingIntentError(503, 'MUTATION_RESULT_UNCERTAIN', '저장 결과를 확인할 수 없습니다. 같은 요청 키를 유지해 주세요.');
  }
  return { status, body: result };
}
