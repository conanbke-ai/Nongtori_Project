import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { decideScoutingAlert } from '../app/features/pests/domain/scouting-policy';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
import {
  processScoutingObservation,
  recordScoutingAction,
  recordScoutingFieldCheck,
} from '../app/features/pests/application/scouting-service';

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
await ensureSchema();
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name >= '0014').sort()) {
  sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
}

const repo = new ScoutingRepository(db);
const t1 = '2026-09-01T09:00:00.000Z';
function insert(table: string, values: Record<string, string | number | null>) {
  const keys = Object.keys(values);
  sqlite.prepare(`INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`).run(...Object.values(values));
}
insert('farms', { id: 'farm-c2', code: 'C2', name: 'C2 테스트농장', status: 'ACTIVE', created_at: t1, updated_at: t1 });
insert('houses', { id: 'house-c2', farm_id: 'farm-c2', code: 'C2', name: 'C2동', status: 'ACTIVE', created_at: t1, updated_at: t1 });
insert('beds', { id: 'bed-23', house_id: 'house-c2', code: '23', name: '23번 베드', status: 'ACTIVE', created_at: t1, updated_at: t1 });
insert('zones', { id: 'zone-g', bed_id: 'bed-23', code: 'G', name: 'G구역', status: 'ACTIVE', created_at: t1, updated_at: t1 });
insert('farm_members', {
  id: 'worker-1', farm_id: 'farm-c2', login_id: 'worker-1', identity_provider: 'SITES', identity_subject: 'worker-1',
  display_name: '작업자', phone: '01000000000', phone_verified_at: t1, notifications_enabled: 1,
  preferred_language: 'ko', role: 'WORKER', status: 'ACTIVE', created_at: t1, updated_at: t1,
});

const baseSignals = {
  hasMeaningfulAnomaly: true,
  matchesRecentKnownPattern: false,
  hasMeaningfulNewEvidence: false,
  worseningTrend: false,
  spatialSpread: false,
  previousFieldCheckFresh: false,
  postTreatmentRebound: false,
};

test('policy never turns no-visible-evidence into a negative diagnosis', () => {
  const decision = decideScoutingAlert({ currentState: 'WATCH', hasActiveCase: true, signals: {
    ...baseSignals, matchesRecentKnownPattern: true, previousFieldCheckFresh: true,
  } });
  assert.equal(decision.alertDecision, 'SUPPRESSED');
  assert.equal(decision.nextState, 'WATCH');
});

test('C2-23-G lifecycle suppresses unchanged repeat and re-alerts only on new worsening evidence', async () => {
  const first = await processScoutingObservation(repo, {
    farmId: 'farm-c2', houseId: 'house-c2', bedId: 'bed-23', zoneId: 'zone-g',
    observedAt: t1, sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
    leafTemp: 31.2, ambientTemp: 28.0, patternFingerprint: 'thermal-pattern-a', signals: baseSignals,
  });
  assert.equal(first.alertDecision, 'ISSUED');
  assert.equal(first.nextState, 'FIELD_CHECK_REQUIRED');
  assert.equal(first.notificationCount, 1);

  const checked = await recordScoutingFieldCheck(repo, {
    farmId: 'farm-c2', locationStateId: first.locationStateId, memberId: 'worker-1',
    evidenceCode: 'NO_VISIBLE_EVIDENCE', checkedAt: '2026-09-01T09:15:00.000Z', observationId: first.observationId,
  });
  assert.equal(checked.nextState, 'WATCH');
  assert.equal(checked.definitiveNegative, false);

  const second = await processScoutingObservation(repo, {
    farmId: 'farm-c2', houseId: 'house-c2', bedId: 'bed-23', zoneId: 'zone-g',
    observedAt: '2026-09-02T09:00:00.000Z', sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
    leafTemp: 31.2, ambientTemp: 28.0, patternFingerprint: 'thermal-pattern-a',
    signals: { ...baseSignals, matchesRecentKnownPattern: true, previousFieldCheckFresh: true },
  });
  assert.equal(second.alertDecision, 'SUPPRESSED');
  assert.equal(second.suppressionReason, 'RECENT_FIELD_CHECK_STILL_FRESH');
  assert.equal(second.notificationCount, 0);

  const third = await processScoutingObservation(repo, {
    farmId: 'farm-c2', houseId: 'house-c2', bedId: 'bed-23', zoneId: 'zone-g',
    observedAt: '2026-09-05T09:00:00.000Z', sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
    leafTemp: 33.1, ambientTemp: 28.0, patternFingerprint: 'thermal-pattern-b',
    signals: { ...baseSignals, hasMeaningfulNewEvidence: true, worseningTrend: true },
  });
  assert.equal(third.alertDecision, 'RECHECK_REQUESTED');
  assert.equal(third.nextState, 'FIELD_CHECK_REQUIRED');
  assert.equal(third.notificationCount, 1);

  const observationCount = sqlite.prepare('SELECT COUNT(*) AS count FROM scouting_observations WHERE location_state_id = ?')
    .get(first.locationStateId) as { count: number };
  assert.equal(Number(observationCount.count), 3, 'suppressed observations must still be stored');
  const alertRows = sqlite.prepare('SELECT alert_decision FROM scouting_alert_events WHERE location_state_id = ? ORDER BY created_at')
    .all(first.locationStateId) as { alert_decision: string }[];
  assert.deepEqual(alertRows.map((row) => row.alert_decision), ['ISSUED', 'SUPPRESSED', 'RECHECK_REQUESTED']);
  const outbox = sqlite.prepare("SELECT COUNT(*) AS count FROM notification_outbox WHERE notification_type = 'PEST_SCOUTING_ALERT'").get() as { count: number };
  assert.equal(Number(outbox.count), 2);
});

test('direct mite evidence confirms; treatment enters post-treatment; rebound escalates', async () => {
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id = 'farm-c2' AND location_key = 'C2:23:G'").get() as { id: string };
  const confirmed = await recordScoutingFieldCheck(repo, {
    farmId: 'farm-c2', locationStateId: location.id, memberId: 'worker-1',
    evidenceCode: 'DIRECT_MITE_OR_EGG_CONFIRMED', checkedAt: '2026-09-05T09:20:00.000Z',
  });
  assert.equal(confirmed.nextState, 'CONFIRMED');

  const action = await recordScoutingAction(repo, {
    farmId: 'farm-c2', locationStateId: location.id, memberId: 'worker-1',
    actionCode: 'TREATMENT_APPLIED', actionAt: '2026-09-05T10:00:00.000Z',
  });
  assert.equal(action.nextState, 'POST_TREATMENT');

  const rebound = await processScoutingObservation(repo, {
    farmId: 'farm-c2', houseId: 'house-c2', bedId: 'bed-23', zoneId: 'zone-g',
    observedAt: '2026-09-08T09:00:00.000Z', sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
    patternFingerprint: 'thermal-pattern-rebound', signals: { ...baseSignals, postTreatmentRebound: true },
  });
  assert.equal(rebound.alertDecision, 'ESCALATED');
  assert.equal(rebound.nextState, 'FIELD_CHECK_REQUIRED');
  assert.equal(rebound.notificationCount, 1);
});
