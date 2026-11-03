// Memory only. No storage, reload recovery, timer, background retry or key rotation.
export type PendingScoutingIntent = { path: string; json: string; key: string; rejected: boolean; uncertain: boolean; memberId: string };
export class ScoutingPendingIntent {
  private value: PendingScoutingIntent | null = null;
  private busy = false;
  constructor(private send: typeof fetch = fetch, private newKey = () => crypto.randomUUID()) {}
  snapshot() { return this.value ? { ...this.value } : null; }
  discardRejected() {
    if (this.value?.rejected && !this.busy) this.value = null;
  }
  private result(path: string, value: unknown) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('INVALID_RESPONSE');
    const payload = value as Record<string, unknown>;
    const expected = path.endsWith('/scouting-field-checks') ? 'fieldCheckId'
      : path.endsWith('/scouting-field-check-corrections') ? 'correctionId'
        : path.endsWith('/scouting-actions') ? 'actionCode' : 'caseId';
    if (typeof payload[expected] !== 'string' || !payload[expected]) throw Error('INVALID_RESPONSE');
    return payload as { message?: string; fieldCheckId?: string; correctionKind?: string; state?: string };
  }
  async confirm(memberId: string, farmId: string) {
    const intent = this.value;
    if (!intent || !intent.uncertain) throw Error('NO_UNCERTAIN_INTENT');
    if (this.busy) throw Error('PENDING_INTENT');
    if (!memberId || intent.memberId !== memberId) throw Error('UNRESOLVED_ACTOR');
    if ((JSON.parse(intent.json) as { farmId?: string }).farmId !== farmId) throw Error('UNRESOLVED_FARM');
    const operations: Record<string, string> = {
      '/api/scouting-field-checks':'CHECK', '/api/scouting-field-check-corrections':'CORRECTION',
      '/api/scouting-actions':'ACTION', '/api/scouting-resolve':'RESOLVE',
    };
    const operation = operations[intent.path];
    if (!operation) throw Error('INVALID_INTENT_PATH');
    this.busy = true;
    try {
      const response = await this.send('/api/scouting-mutation-status', { method: 'POST', headers: {
        'content-type':'application/json', 'Idempotency-Key':intent.key, 'Scouting-Operation':operation,
      }, body:intent.json, cache:'no-store' });
      const result: unknown = await response.json();
      if (!result || typeof result !== 'object' || Array.isArray(result)) throw Error('INVALID_RESPONSE');
      const value = result as { state?: string; originalStatus?: number; result?: unknown; error?: string };
      if (!response.ok) throw Error(value.error || 'CONFIRMATION_UNAVAILABLE');
      if (value.state === 'UNCONFIRMED') return { state:'UNCONFIRMED' as const };
      if (value.state !== 'COMMITTED' || value.originalStatus !== (operation === 'RESOLVE' ? 200 : 201)) throw Error('INVALID_RESPONSE');
      const payload = this.result(intent.path, value.result);
      this.value = null;
      return { state:'COMMITTED' as const, result:payload };
    } finally { this.busy = false; }
  }
  async request(path: string, body: Record<string, unknown>, memberId: string) {
    if (!memberId?.trim()) throw Error('UNVERIFIED_ACTOR');
    const json = JSON.stringify(body);
    if (this.busy) throw Error('PENDING_INTENT');
    if (this.value && this.value.memberId !== memberId) throw Error('UNRESOLVED_ACTOR');
    if (this.value && (this.value.path !== path || this.value.json !== json)) throw Error('UNRESOLVED_INTENT');
    this.value ??= { path, json, key: this.newKey(), rejected: false, uncertain: false, memberId };
    const intent = this.value;
    this.busy = true;
    intent.rejected = false; // every new send can have an ambiguous outcome
    try {
      const response = await this.send(path, { method: 'POST', headers: {
        'content-type': 'application/json', 'Idempotency-Key': intent.key,
      }, body: intent.json });
      const result: unknown = await response.json();
      if (!result || typeof result !== 'object' || Array.isArray(result)) throw Error('INVALID_RESPONSE');
      if (!response.ok) {
        // Only definite, pre-commit/rolled-back rejection can be explicitly discarded.
        const code = (result as { code?: string }).code;
        intent.rejected = !intent.uncertain && [400,403,422,429].includes(response.status) && typeof code === 'string' &&
          ['INVALID_INTENT','INVALID_REQUEST_KEY','INTENT_TOO_LARGE','FORBIDDEN','TARGET_NOT_FOUND','INVALID_MUTATION','RESPONSE_TOO_LARGE','RECEIPT_LIMIT'].includes(code);
        throw Error((result as { error?: string }).error || 'MUTATION_REJECTED');
      }
      const payload = this.result(path, result);
      this.value = null;
      return payload;
    } catch (error) {
      // A later rejection cannot prove an earlier in-flight request never committed.
      if (!intent.rejected) intent.uncertain = true;
      throw error;
    } finally { this.busy = false; }
  }
}
