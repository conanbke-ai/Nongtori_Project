export const historyLimit = 50;
const families = {
  observations: ['observed_at', 'source_type'], fieldChecks: ['checked_at', 'primary_evidence_code'],
  corrections: ['created_at', 'correction_kind'], actions: ['action_at', 'action_code'],
  alerts: ['created_at', 'alert_decision'], caseEvents: ['created_at', 'event_type'],
} as const;
export type HistoryKind = keyof typeof families;
export type HistoryEntry = { kind: HistoryKind; id: string; at: string | null; code: string;
  originalCheckId: string | null; replacementCode: string | null };
export type HistoryLoadState = { scope: string; status: 'idle' | 'loading' | 'ready' | 'stale' | 'error'; entries: HistoryEntry[] };
export const historyScope = (farmId: string, locationId: string) => JSON.stringify([farmId, locationId]);
class HistoryReadError extends Error {
  constructor(readonly discardPrevious: boolean) { super('HISTORY_UNAVAILABLE'); }
}
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new HistoryReadError(true);
  return value as Record<string, unknown>;
}
export function timestamp(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(value);
  if (!parts) return null;
  const [year, month, day, hour, minute, second] = parts.slice(1, 7).map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1] ?? 0;
  if (month < 1 || month > 12 || day < 1 || day > days || hour > 23 || minute > 59 || second > 59) return null;
  return Number.isFinite(Date.parse(value)) ? value : null;
}

// Project immutable source rows; do not infer a diagnosis or apply corrections.
export function projectScoutingHistory(payload: unknown, farmId: string, locationId: string): HistoryEntry[] {
  const data = record(payload), location = record(data.location);
  if (location.id !== locationId || location.farm_id !== farmId) throw new HistoryReadError(true);
  const entries: HistoryEntry[] = [];
  for (const kind of Object.keys(families) as HistoryKind[]) {
    const rows = data[kind];
    if (!Array.isArray(rows) || rows.length > historyLimit) throw new HistoryReadError(true);
    const [timeKey, codeKey] = families[kind];
    for (const value of rows) {
      const row = record(value);
      if (typeof row.id !== 'string' || !row.id || row.farm_id !== farmId || row.location_state_id !== locationId ||
        typeof row[codeKey] !== 'string') throw new HistoryReadError(true);
      const at = row[timeKey];
      entries.push({ kind, id: row.id, at: timestamp(at),
        code: row[codeKey], originalCheckId: kind === 'corrections' && typeof row.field_check_id === 'string' ? row.field_check_id : null,
        replacementCode: kind === 'corrections' && typeof row.replacement_evidence_code === 'string' ? row.replacement_evidence_code : null });
    }
  }
  return entries.sort((a, b) => (b.at ? Date.parse(b.at) : -Infinity) - (a.at ? Date.parse(a.at) : -Infinity) ||
    a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
}

export class ScoutingHistoryReader {
  private sequence = 0;
  private busyScope: string | null = null;
  private previous: HistoryLoadState | null = null;
  constructor(private read: typeof fetch = fetch) {}
  invalidate() { this.sequence++; this.busyScope = null; this.previous = null; }
  async load(farmId: string, locationId: string, publish: (state: HistoryLoadState) => void) {
    if (!farmId || !locationId) return;
    const scope = historyScope(farmId, locationId);
    if (this.busyScope === scope) return;
    const id = ++this.sequence, previous = this.previous?.scope === scope ? this.previous.entries : [];
    this.busyScope = scope;
    publish({ scope, status: 'loading', entries: previous });
    try {
      const query = new URLSearchParams({ farmId, locationStateId: locationId, limit: String(historyLimit) });
      const read = this.read;
      const response = await read(`/api/scouting-history?${query}`, { method: 'GET', cache: 'no-store' });
      if (!response.ok) throw new HistoryReadError([401, 403, 404, 422].includes(response.status));
      const entries = projectScoutingHistory(await response.json(), farmId, locationId);
      if (id !== this.sequence) return;
      this.previous = { scope, status: 'ready', entries }; publish(this.previous);
    } catch (error) {
      if (id !== this.sequence) return;
      const entries = error instanceof HistoryReadError && error.discardPrevious ? [] : previous;
      this.previous = entries.length ? { scope, status: 'stale', entries } : null;
      publish({ scope, status: entries.length ? 'stale' : 'error', entries });
    } finally { if (id === this.sequence) this.busyScope = null; }
  }
}
