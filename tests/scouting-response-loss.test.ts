// Characterization of current delivery semantics, not an idempotency acceptance gate.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { DatabaseSync } from 'node:sqlite';
import { test } from 'node:test';

const sqlite = new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys = ON');
for (const file of readdirSync('drizzle').filter(name => name.endsWith('.sql') && name < '0014').sort()) {
  sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
}
function prepare(sql: string) {
  let args: (string | number | null)[] = [];
  return {
    bind(...values: (string | number | null)[]) { args = values; return this; },
    async all<T>() { return { results: sqlite.prepare(sql).all(...args) as T[], success: true, meta: {} }; },
    async first<T>() { return (sqlite.prepare(sql).get(...args) as T | undefined) ?? null; },
    async run() { return { success: true, meta: { changes: Number(sqlite.prepare(sql).run(...args).changes) } }; },
  };
}
const db = { prepare, async batch(statements: ReturnType<typeof prepare>[]) {
  sqlite.exec('BEGIN');
  try {
    const results = [];
    for (const statement of statements) results.push(await statement.run());
    sqlite.exec('COMMIT');
    return results;
  } catch (error) { sqlite.exec('ROLLBACK'); throw error; }
} } as unknown as D1Database;
(globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = { DB: db };
const { ensureSchema } = await import('../db');
const { ensureScoutingRuntime } = await import('../db/scouting-runtime');
await ensureSchema();
await ensureScoutingRuntime();
const stamp = '2026-10-30T09:00:00.000Z';
function insert(table: string, values: Record<string, string | number | null>) {
  const columns = sqlite.prepare(`PRAGMA table_info(${table})`).all() as { name: string; notnull: number; dflt_value: unknown; type: string }[];
  for (const column of columns) if (!(column.name in values) && column.notnull && column.dflt_value === null) {
    values[column.name] = column.type.includes('INT') ? 0 : 'TEST_ONLY';
  }
  const keys = Object.keys(values);
  sqlite.prepare(`INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`).run(...Object.values(values));
}
insert('farms', { id: 'farm-loss', code: 'LOSS', name: 'TEST_ONLY', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('houses', { id: 'house-loss', farm_id: 'farm-loss', code: 'H', name: 'TEST_ONLY', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('beds', { id: 'bed-loss', house_id: 'house-loss', code: 'B', name: 'TEST_ONLY', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('zones', { id: 'zone-loss', bed_id: 'bed-loss', code: 'Z', name: 'TEST_ONLY', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('farm_members', { id: 'member-loss', farm_id: 'farm-loss', login_id: 'member-loss', identity_provider: 'SITES', identity_subject: 'member-loss', display_name: 'TEST_ONLY', role: 'OWNER', status: 'ACTIVE', created_at: stamp, updated_at: stamp });

const checks = await import('../app/api/scouting-field-checks/route');
const corrections = await import('../app/api/scouting-field-check-corrections/route');
const actions = await import('../app/api/scouting-actions/route');
const resolve = await import('../app/api/scouting-resolve/route');
const { ScoutingRepository } = await import('../app/features/pests/infrastructure/scouting-repository');
const { processScoutingObservation } = await import('../app/features/pests/application/scouting-service');
const observed = await processScoutingObservation(new ScoutingRepository(db), {
  farmId: 'farm-loss', houseId: 'house-loss', bedId: 'bed-loss', zoneId: 'zone-loss', observedAt: stamp,
  sourceType: 'FUSION', signals: { hasMeaningfulAnomaly: true, hasMeaningfulNewEvidence: true,
    matchesRecentKnownPattern: false, worseningTrend: false, spatialSpread: false,
    previousFieldCheckFresh: false, postTreatmentRebound: false },
});
const scope = { farmId: 'farm-loss', locationStateId: observed.locationStateId };
function request(path: string, body: object) {
  return new Request(`https://nongtori.test/api/${path}`, { method: 'POST',
    headers: { 'content-type': 'application/json', 'oai-authenticated-user-id': 'member-loss' }, body: JSON.stringify(body) });
}
const count = (table: string) => Number((sqlite.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n);
const version = () => Number((sqlite.prepare('SELECT state_version FROM scouting_location_states WHERE id = ?').get(observed.locationStateId) as { state_version: number }).state_version);

async function loseResponse(handler: (request: Request) => Promise<Response>, path: string, body: object) {
  // Execute and assert the server commit, then discard its response at the client boundary.
  const response = await handler(request(path, body));
  assert.ok(response.ok, `first server response: ${response.status}`);
  throw new TypeError('TEST_ONLY: response lost after server commit');
}

test('response-loss replay appends checks, corrections and actions; resolve replay reports no active case', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('External network forbidden in fixture'); };
  try {
    const checkBody = { ...scope, evidenceCode: 'NO_VISIBLE_EVIDENCE', checkedAt: stamp };
    const checkVersion = version();
    await assert.rejects(loseResponse(checks.POST, 'scouting-field-checks', checkBody), /response lost/);
    assert.equal(count('scouting_field_checks'), 1);
    const firstCheck = sqlite.prepare('SELECT id FROM scouting_field_checks').get() as { id: string };
    const checkReplay = await checks.POST(request('scouting-field-checks', checkBody));
    assert.equal(checkReplay.status, 201);
    assert.notEqual((await checkReplay.json() as { fieldCheckId: string }).fieldCheckId, firstCheck.id);
    assert.equal(count('scouting_field_checks'), 2);
    assert.equal(version(), checkVersion + 2);

    const correctionBody = { farmId: scope.farmId, fieldCheckId: firstCheck.id, correctionKind: 'REPLACE',
      replacementEvidenceCode: 'DIRECT_MITE_OR_EGG_CONFIRMED', reasonCode: 'MISCLICK', correctedAt: stamp };
    await assert.rejects(loseResponse(corrections.POST, 'scouting-field-check-corrections', correctionBody), /response lost/);
    assert.equal(count('scouting_field_check_corrections'), 1);
    const correctionReplay = await corrections.POST(request('scouting-field-check-corrections', correctionBody));
    assert.equal(correctionReplay.status, 201);
    assert.equal(count('scouting_field_check_corrections'), 2);
    assert.equal(Number((sqlite.prepare("SELECT COUNT(*) AS n FROM scouting_case_events WHERE event_type='FIELD_CHECK_CORRECTED'").get() as { n: number }).n), 2);

    const actionBody = { ...scope, actionCode: 'TREATMENT_APPLIED', actionAt: stamp };
    await assert.rejects(loseResponse(actions.POST, 'scouting-actions', actionBody), /response lost/);
    assert.equal(count('scouting_actions'), 1);
    const actionReplay = await actions.POST(request('scouting-actions', actionBody));
    assert.equal(actionReplay.status, 201);
    assert.equal(count('scouting_actions'), 2);

    const resolveBody = { ...scope, reasonCode: 'TREATMENT_COMPLETED', resolvedAt: stamp };
    await assert.rejects(loseResponse(resolve.POST, 'scouting-resolve', resolveBody), /response lost/);
    const resolveReplay = await resolve.POST(request('scouting-resolve', resolveBody));
    assert.equal(resolveReplay.status, 400);
    assert.match((await resolveReplay.json() as { error: string }).error, /진행 중 예찰 건이 없습니다/);
    assert.equal(Number((sqlite.prepare("SELECT COUNT(*) AS n FROM scouting_case_events WHERE event_type='RESOLVED'").get() as { n: number }).n), 1);
  } finally { globalThis.fetch = originalFetch; sqlite.close(); }
});
