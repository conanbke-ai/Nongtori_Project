import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
import {
  correctScoutingFieldCheck,
  processScoutingObservation,
  recordScoutingAction,
  recordScoutingFieldCheck,
  resolveScoutingCase,
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

test('fresh runtime bootstrap creates scouting v2 tables, policy and disables legacy stateless trigger', () => {
  for (const table of ['scouting_location_states', 'scouting_cases', 'scouting_case_links', 'scouting_policy_profiles', 'scouting_observations', 'scouting_field_checks', 'scouting_field_check_corrections', 'scouting_actions', 'scouting_case_events', 'scouting_alert_events']) {
    assert.ok(sqlite.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name = ?").get(table));
  }
  const profile = sqlite.prepare("SELECT freshness_mode, field_check_freshness_minutes FROM scouting_policy_profiles WHERE status='ACTIVE'").get() as { freshness_mode: string; field_check_freshness_minutes: number | null };
  assert.equal(profile.freshness_mode, 'CALIBRATION_PENDING');
  assert.equal(profile.field_check_freshness_minutes, null, 'freshness duration must remain unset before field calibration');
  const trigger = sqlite.prepare("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='trg_mite_alert_notification_outbox_v3'").get() as { sql: string };
  assert.match(trigger.sql, /WHEN 0/);
});

test('field evidence corrects a mite-suspect case into the observed issue family', async () => {
  const first = await processScoutingObservation(repo, {
    farmId: 'farm-hardening', houseId: 'house-h', bedId: 'bed-h', zoneId: 'zone-h',
    observedAt: stamp, sourceType: 'FUSION', issueFamily: 'PEST', issueCode: 'SPIDER_MITE', signals: baseSignals,
  });
  const check = await recordScoutingFieldCheck(repo, {
    farmId: 'farm-hardening', locationStateId: first.locationStateId, memberId: 'worker-h',
    evidenceCode: 'DISEASE_LIKE_EVIDENCE', checkedAt: '2026-09-16T09:10:00.000Z',
  });
  const row = sqlite.prepare('SELECT issue_family, primary_issue_code FROM scouting_cases WHERE id = ?').get(first.caseId) as { issue_family: string; primary_issue_code: string };
  assert.equal(row.issue_family, 'DISEASE');
  assert.equal(row.primary_issue_code, 'UNKNOWN_DISEASE');
  assert.ok(check.fieldCheckId);
});

test('field check correction is append-only and updates current interpretation', async () => {
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id='farm-hardening'").get() as { id: string };
  const check = await recordScoutingFieldCheck(repo, {
    farmId: 'farm-hardening', locationStateId: location.id, memberId: 'worker-h',
    evidenceCode: 'DISEASE_LIKE_EVIDENCE', checkedAt: '2026-09-16T09:12:00.000Z',
  });
  await correctScoutingFieldCheck(repo, {
    farmId: 'farm-hardening', fieldCheckId: check.fieldCheckId, memberId: 'worker-h',
    correctionKind: 'REPLACE', replacementEvidenceCode: 'DIRECT_MITE_OR_EGG_CONFIRMED',
    reasonCode: 'MISCLICK', correctedAt: '2026-09-16T09:13:00.000Z',
  });
  const original = sqlite.prepare('SELECT primary_evidence_code FROM scouting_field_checks WHERE id = ?').get(check.fieldCheckId) as { primary_evidence_code: string };
  assert.equal(original.primary_evidence_code, 'DISEASE_LIKE_EVIDENCE', 'original field check must remain immutable');
  const correction = sqlite.prepare('SELECT replacement_evidence_code FROM scouting_field_check_corrections WHERE field_check_id = ? ORDER BY created_at DESC LIMIT 1').get(check.fieldCheckId) as { replacement_evidence_code: string };
  assert.equal(correction.replacement_evidence_code, 'DIRECT_MITE_OR_EGG_CONFIRMED');
  const state = sqlite.prepare('SELECT current_state FROM scouting_location_states WHERE id = ?').get(location.id) as { current_state: string };
  assert.equal(state.current_state, 'CONFIRMED');
});

test('explicit resolve closes the episode and a later anomaly opens a linked recurrence case', async () => {
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id='farm-hardening'").get() as { id: string };
  const active = await repo.activeCase(location.id);
  assert.ok(active);
  await resolveScoutingCase(repo, {
    farmId: 'farm-hardening', locationStateId: location.id, memberId: 'worker-h',
    reasonCode: 'TREATMENT_COMPLETED', resolvedAt: '2026-09-16T10:00:00.000Z',
  });
  const closed = sqlite.prepare('SELECT status, close_reason FROM scouting_cases WHERE id = ?').get(active!.id) as { status: string; close_reason: string };
  assert.equal(closed.status, 'RESOLVED');
  assert.equal(closed.close_reason, 'TREATMENT_COMPLETED');

  const recurrence = await processScoutingObservation(repo, {
    farmId: 'farm-hardening', houseId: 'house-h', bedId: 'bed-h', zoneId: 'zone-h',
    observedAt: '2026-09-18T09:00:00.000Z', sourceType: 'THERMAL', issueFamily: 'PEST', issueCode: 'SPIDER_MITE',
    signals: { ...baseSignals, hasMeaningfulNewEvidence: true },
  });
  assert.notEqual(recurrence.caseId, active!.id);
  const link = sqlite.prepare('SELECT previous_case_id FROM scouting_case_links WHERE case_id = ?').get(recurrence.caseId) as { previous_case_id: string };
  assert.equal(link.previous_case_id, active!.id);
});

test('fixed-window freshness is versioned and calculated by runtime once configured', async () => {
  sqlite.prepare("UPDATE scouting_policy_profiles SET status='RETIRED' WHERE status='ACTIVE'").run();
  insert('scouting_policy_profiles', {
    policy_version: 'TEST-FRESH-60', freshness_mode: 'FIXED_WINDOW', field_check_freshness_minutes: 60,
    status: 'ACTIVE', created_at: '2026-09-16T10:00:00.000Z',
  });
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id='farm-hardening'").get() as { id: string };
  await recordScoutingFieldCheck(repo, {
    farmId: 'farm-hardening', locationStateId: location.id, memberId: 'worker-h',
    evidenceCode: 'NO_VISIBLE_EVIDENCE', checkedAt: '2026-09-18T10:00:00.000Z',
  });
  const result = await processScoutingObservation(repo, {
    farmId: 'farm-hardening', houseId: 'house-h', bedId: 'bed-h', zoneId: 'zone-h',
    observedAt: '2026-09-18T10:30:00.000Z', sourceType: 'THERMAL', patternFingerprint: 'same-fresh-pattern',
    signals: { ...baseSignals, matchesRecentKnownPattern: true, previousFieldCheckFresh: false },
  });
  assert.equal(result.freshnessSource, 'VERSIONED_FIXED_WINDOW');
  assert.equal(result.policyVersion, 'TEST-FRESH-60');
  assert.equal(result.alertDecision, 'SUPPRESSED');
});

test('observation rejects a frame from another farm or mismatched location scope', async () => {
  insert('farms', { id: 'farm-other', code: 'FO', name: 'Other Farm', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
  insert('capture_sessions', { id: 'session-other', farm_id: 'farm-other', capture_mode: 'VIDEO', source_type: 'VIDEO_IMPORT', processing_status: 'COMPLETED', started_at: stamp, created_at: stamp });
  insert('video_assets', { id: 'video-other', capture_session_id: 'session-other', modality: 'RGB', processing_status: 'COMPLETED', created_at: stamp });
  insert('frames', { id: 'frame-other', video_asset_id: 'video-other', capture_session_id: 'session-other', frame_index: 1, timestamp_ms: 0, processing_status: 'COMPLETED', created_at: stamp });
  await assert.rejects(() => processScoutingObservation(repo, {
    farmId: 'farm-hardening', houseId: 'house-h', bedId: 'bed-h', zoneId: 'zone-h',
    observedAt: '2026-09-18T11:00:00.000Z', sourceType: 'FUSION', frameId: 'frame-other', signals: baseSignals,
  }), /관측 프레임이 선택한 농장과 일치하지 않습니다/);
});

test('post-treatment and monitoring states are not treated as immediate attention work', async () => {
  const location = sqlite.prepare("SELECT id FROM scouting_location_states WHERE farm_id='farm-hardening'").get() as { id: string };
  await recordScoutingAction(repo, {
    farmId: 'farm-hardening', locationStateId: location.id, memberId: 'worker-h',
    actionCode: 'TREATMENT_APPLIED', actionAt: '2026-09-18T12:00:00.000Z',
  });
  assert.equal((sqlite.prepare('SELECT current_state FROM scouting_location_states WHERE id = ?').get(location.id) as { current_state: string }).current_state, 'POST_TREATMENT');

  const { GET } = await import('../app/api/scouting-locations/route');
  const response = await GET(new Request('http://localhost/api/scouting-locations?farmId=farm-hardening&attention=1'));
  assert.equal(response.status, 200);
  const payload = await response.json() as { rows: { id: string; current_state: string }[] };
  assert.equal(payload.rows.some((row) => row.id === location.id), false);
});
