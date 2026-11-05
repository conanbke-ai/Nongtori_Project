import { timestamp, type HistoryEntry } from './scouting-history-reader';

export type OriginalState = { scope: string; status: 'idle' | 'loading' | 'ready' | 'missing' | 'denied' | 'error'; entry: HistoryEntry | null };
export const originalScope = (farmId: string, locationId: string, checkId: string) => JSON.stringify([farmId, locationId, checkId]);

export class ScoutingOriginalReader {
  private sequence = 0;
  private busy: string | null = null;
  constructor(private read: typeof fetch = fetch) {}
  invalidate() { this.sequence++; this.busy = null; }
  async load(farmId: string, locationId: string, checkId: string, publish: (state: OriginalState) => void) {
    if (!farmId || !locationId || !checkId) return;
    const scope = originalScope(farmId, locationId, checkId);
    if (this.busy === scope) return;
    const sequence = ++this.sequence;
    this.busy = scope;
    const emit = (status: OriginalState['status'], entry: HistoryEntry | null = null) => {
      if (sequence === this.sequence) publish({ scope, status, entry });
    };
    emit('loading');
    try {
      const query = new URLSearchParams({ farmId, locationStateId: locationId, fieldCheckId: checkId });
      const response = await this.read(`/api/scouting-original-check?${query}`, { method: 'GET', cache: 'no-store' });
      if (!response.ok) { emit(response.status === 404 ? 'missing' : [401, 403].includes(response.status) ? 'denied' : 'error'); return; }
      const data: unknown = await response.json();
      const row = data && typeof data === 'object' && 'original' in data ? data.original : null;
      if (!row || typeof row !== 'object' || !('id' in row) || row.id !== checkId ||
        !('farm_id' in row) || row.farm_id !== farmId || !('location_state_id' in row) || row.location_state_id !== locationId ||
        !('primary_evidence_code' in row) || typeof row.primary_evidence_code !== 'string') throw Error('INVALID_ORIGINAL');
      emit('ready', { kind: 'fieldChecks', id: checkId, code: row.primary_evidence_code,
        at: timestamp('checked_at' in row ? row.checked_at : null), originalCheckId: null, replacementCode: null });
    } catch { emit('error'); }
    finally { if (sequence === this.sequence) this.busy = null; }
  }
}
