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
      const payload = result as Record<string, unknown>;
      const expected = path.endsWith('/scouting-field-checks') ? 'fieldCheckId'
        : path.endsWith('/scouting-field-check-corrections') ? 'correctionId'
          : path.endsWith('/scouting-actions') ? 'actionCode' : 'caseId';
      if (typeof payload[expected] !== 'string' || !payload[expected]) throw Error('INVALID_RESPONSE');
      this.value = null;
      return result as { message?: string; fieldCheckId?: string; correctionKind?: string; state?: string };
    } catch (error) {
      // A later rejection cannot prove an earlier in-flight request never committed.
      if (!intent.rejected) intent.uncertain = true;
      throw error;
    } finally { this.busy = false; }
  }
}
