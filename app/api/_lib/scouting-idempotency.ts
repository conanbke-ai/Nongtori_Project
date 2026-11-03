import { env } from 'cloudflare:workers';
import { getFarmMember } from '@/app/lib/farm-auth';
import { executeScoutingIntent, lookupScoutingIntent, normalizeScoutingIntent, ScoutingIntentError, type ScoutingMutationKind } from '@/app/features/pests/application/scouting-intent';

async function boundedJson(request: Request) {
  const reader = request.body?.getReader();
  if (!reader) throw new ScoutingIntentError(422, 'INVALID_INTENT', '입력을 확인해 주세요.');
  const chunks: Uint8Array[] = []; let bytes = 0;
  for (;;) {
    const { done, value } = await reader.read(); if (done) break;
    bytes += value.byteLength;
    if (bytes > 16384) { await reader.cancel(); throw new ScoutingIntentError(422, 'INTENT_TOO_LARGE', '입력이 너무 큽니다.'); }
    chunks.push(value);
  }
  const buffer = new Uint8Array(bytes); let offset = 0;
  for (const chunk of chunks) { buffer.set(chunk, offset); offset += chunk.byteLength; }
  try {
    const body: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(buffer));
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw Error('object required');
    return body as Record<string, unknown>;
  } catch { throw new ScoutingIntentError(422, 'INVALID_INTENT', '입력을 확인해 주세요.'); }
}
function configuredLimit(value: unknown) {
  if (typeof value !== 'string' || !/^[1-9]\d*$/.test(value)) return null;
  const n = Number(value); return Number.isSafeInteger(n) ? n : null;
}
export async function handleScoutingIntentLookup(request: Request) {
  const respond = (body: unknown, status = 200) => Response.json(body, { status,
    headers: { 'Cache-Control': 'no-store', 'Vary': 'Idempotency-Key, Scouting-Operation' } });
  try {
    const key = request.headers.get('Idempotency-Key') ?? '';
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(key))
      throw new ScoutingIntentError(422, 'INVALID_REQUEST_KEY', '요청 키를 확인해 주세요.');
    const operation = request.headers.get('Scouting-Operation') ?? '';
    if (!['CHECK','CORRECTION','ACTION','RESOLVE'].includes(operation))
      throw new ScoutingIntentError(422, 'INVALID_INTENT', '조회할 요청을 확인해 주세요.');
    if (env.SCOUTING_MUTATION_IDEMPOTENCY !== 'true')
      throw new ScoutingIntentError(503, 'IDEMPOTENCY_DISABLED', '요청 기록 기능이 활성화되지 않았습니다.');
    const intent = normalizeScoutingIntent(operation as ScoutingMutationKind, await boundedJson(request));
    const actor = await getFarmMember(request, intent.farmId);
    if (!actor?.id || !actor.permissions.reviewAlerts)
      throw new ScoutingIntentError(403, 'FORBIDDEN', '이 농장의 요청 결과를 확인할 권한이 없습니다.');
    // Lookup never calls original POST handler, bootstrap or a write transaction.
    return respond(await lookupScoutingIntent(env.DB, actor.id, key, intent));
  } catch (error) {
    if (error instanceof ScoutingIntentError) return respond({ error: error.message, code: error.code }, error.status);
    return respond({ error: '아직 저장 결과를 확인할 수 없습니다. 기존 요청 키를 유지해 주세요.', code: 'MUTATION_RESULT_UNCERTAIN' }, 503);
  }
}
export async function handleKeyedScoutingMutation(request: Request, operation: ScoutingMutationKind) {
  try {
    const key = request.headers.get('Idempotency-Key') ?? '';
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(key))
      throw new ScoutingIntentError(422, 'INVALID_REQUEST_KEY', '요청 키를 확인해 주세요.');
    const farm = configuredLimit(env.SCOUTING_RECEIPT_FARM_LIMIT), member = configuredLimit(env.SCOUTING_RECEIPT_MEMBER_LIMIT);
    if (env.SCOUTING_MUTATION_IDEMPOTENCY !== 'true' || !farm || !member)
      throw new ScoutingIntentError(503, 'IDEMPOTENCY_DISABLED', '요청 기록 기능이 활성화되지 않았습니다.');
    const intent = normalizeScoutingIntent(operation, await boundedJson(request));
    const actor = await getFarmMember(request, intent.farmId);
    if (!actor?.id || !actor.permissions.reviewAlerts)
      throw new ScoutingIntentError(403, 'FORBIDDEN', '이 농장의 예찰 기록을 변경할 권한이 없습니다.');
    // No ensureSchema/ensureScoutingRuntime: schema preparation is not activation.
    const result = await executeScoutingIntent(env.DB, actor.id, key, intent, { farm, member });
    return Response.json(result.body, { status: result.status });
  } catch (error) {
    if (error instanceof ScoutingIntentError)
      return Response.json({ error: error.message, code: error.code }, { status: error.status });
    return Response.json({ error: '저장 결과를 확인할 수 없습니다. 같은 요청 키를 유지해 주세요.', code: 'MUTATION_RESULT_UNCERTAIN' }, { status: 503 });
  }
}
