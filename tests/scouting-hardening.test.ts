import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
import { processScoutingObservation, recordScoutingAction, recordScoutingFieldCheck } from '../app/features/pests/application/scouting-service';

const sqlite = new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys = ON');
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name < '0014').sort()) {
  sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
}
function prepare(sql: string) {
  const statement = () => sqlite.prepare(sql);
  let args: (string | number | null)[] = [];
  return {
    bind(...values: (string | number | null)[]) { args = values; return this; },
    async all<T>() { return { results: statement().all(...args) as T[], success: true, meta: {} }; },
    async first<T>() { return (statement().get(...args) as T | undefined) ?? null; },
    async run() { const result = statement().run(...args); return { success: true, meta: { changes: Number(result.changes) } }; },
  };
}
const db = { prepare, async batch(statements: ReturnType<typeof prepare>[]) {
  sqlite.exec('BEGIN');
  try { const results = []; for (const statement of statements) results.push(await statement.run()); sqlite.exec('COMMIT'); return results; }
  catch (error) { sqlite.exec('ROLLBACK'); throw error; }
} } as unknown as D1Database;
(globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = {
  DB: db,
  FILES: { async put() {}, async delete() {} },
};
const { ensureSchema } = await import('../db');
const { ensureScoutingRuntime } = await import('../db/scouting-runtime');
await ensureSchema();
await ensureScoutingRuntime();

const stamp = '2026-09-16T09:00:00.000Z';
function insert(table: string, values: Record<string, string | number | null>) {
  const rows = sqlite.prepare(`PRAGMA table_info(${table})`).all() as { name: string; notnull: number; dflt_value: unknown; type: string }[];
  for (const column of rows) if (!(column.name in values) && column.notnull && column.dflt_value === null) {
    values[column.name] = column.type.toUpperCase().includes('INT') ? 0 : 'TEST_ONLY';
  }
  const keys = Object.keys(values);
  sqlite.prepare(`INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`).run(...Object.values(values));
}
insert('farms', { id: 'farm-hardening', code: 'FH', name: 'Hardening Farm', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('houses', { id: 'house-h', farm_id: 'farm-hardening', code: 'H1', name: 'H1', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('beds', { id: 'bed-h', house_id: 'house-h', code: 'B1', name: 'B1', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('zones', { id: 'zone-h', bed_id: 'bed-h', code: 'Z1', name: 'Z1', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
insert('farm_members', { id: 'worker-h', farm_id: 'farm-hardening', login_id: 'worker-h', identity_provider: 'SITES', identity_subject: 'worker-h', role: 'WORKER', status: 'ACTIVE', display_name: 'worker', created_at: stamp, updated_at: stamp });

const repo = new ScoutingRepository(db);
const baseSignals = {
  hasMeaningfulAnomaly: true,
  matchesRecentKnownPattern: false,
  hasMeaningfulNewEvidence: false,
  worseningTrend: false,
  spatialSpread: false,
  previousFieldCheckFresh: false,
  postTreatmentRebound: false,
};

test('fresh runtime bootstrap creates scouting tables, full catalog seeds, and disables legacy stateless trigger', () => {
  for (const table of ['scouting_location_states', 'scouting_cases', 'scouting_observations', 'scouting_field_checks', 'scouting_actions', 'scouting_alert_events']) {
    assert.ok(sqlite.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name = ?").get(table));
  }
  const codes = sqlite.prepare('SELECT code FROM scouting_issue_catalog ORDER BY code').all() as { code: string }[];
  for (const code of ['SPIDER_MITE', 'APHID', 'THRIPS', 'POWDERY_MILDEW', 'GRAY_MOLD', 'UNKNOWN_PEST', 'UNKNOWN_DISEASE', 'ENVIRONMENTAL_STRESS']) {
    assert.ok(codes.some((row) => row.code === code), `${code} must exist in runtime catalog`);
  }
  const trigger = sqlite.prepare("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='trg_mite_alert_notification_outbox_v3'").get() as { sql: string };
  assert.match(trigger.sql, /WHEN 0/);
});

test('field evidence corrects a mite-suspect case into the observed issue family', async () => {
  const first = await processScoutingObservation(repo, {
    farmId: 'farm-hardening', houseId: 'house-h', bedId: 'bed-h', zoneId: 'zone-h',
    observedAt: stamp, sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE', signals: baseSignals,
  });
  await recordScoutingFieldCheck(repo, {
    farmId: 'farm-hardening', locationStateId: first.locationStateId, memberId: 'worker-h',
    evidenceCode: 'DISEASE_LIKE_EVIDENCE', checkedAt: '2026-09-16T09:10:00.000Z',
  });
  const row = sqlite.prepare('SELECT issue_family, primary_issue_code FROM scouting_cases WHERE id = ?').get(first.caseId) as { issue_family: string; primary_issue_code: string };
  assert.equal(row.issue_family, 'DISEASE');
  assert.equal(row.primary_issue_code, 'UNKNOWN_DISEASE');
});

test('post-treatment and monitoring states are not treated as immediate attention work', async () => {
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id='farm-hardening'").get() as { id: string };
  await recordScoutingAction(repo, {
    farmId: 'farm-hardening', locationStateId: location.id, memberId: 'worker-h',
    actionCode: 'TREATMENT_APPLIED', actionAt: '2026-09-16T09:20:00.000Z',
  });
  assert.equal((sqlite.prepare('SELECT current_state FROM scouting_location_states WHERE id = ?').get(location.id) as { current_state: string }).current_state, 'POST_TREATMENT');

  const { GET } = await import('../app/api/scouting-locations/route');
  const response = await GET(new Request('http://localhost/api/scouting-locations?farmId=farm-hardening&attention=1'));
  assert.equal(response.status, 200);
  const payload = await response.json() as { rows: { id: string; current_state: string }[] };
  assert.equal(payload.rows.some((row) => row.id === location.id), false);
});
