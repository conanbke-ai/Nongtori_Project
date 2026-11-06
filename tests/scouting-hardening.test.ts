import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
import { projectScoutingHistory } from '../app/features/pests/presentation/scouting-history-reader';
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
  const response = await GET(new Request(
    'https://nongtori.test/api/scouting-locations?farmId=farm-hardening&attention=1',
    { headers: { 'oai-authenticated-user-id': 'worker-h' } },
  ));
  assert.equal(response.status, 200);
  const payload = await response.json() as { rows: { id: string; current_state: string }[] };
  assert.equal(payload.rows.some((row) => row.id === location.id), false);
});

test('location history GET keeps original and correction evidence, projects actual SQL and rejects foreign/revoked members',async()=>{
  insert('farms',{id:'history-farm',code:'HF',name:'SYNTHETIC',status:'ACTIVE',created_at:stamp,updated_at:stamp});
  insert('houses',{id:'history-house',farm_id:'history-farm',code:'HH',name:'SYNTHETIC',status:'ACTIVE',created_at:stamp,updated_at:stamp});
  insert('beds',{id:'history-bed',house_id:'history-house',code:'HB',name:'SYNTHETIC',status:'ACTIVE',created_at:stamp,updated_at:stamp});
  insert('zones',{id:'history-zone',bed_id:'history-bed',code:'HZ',name:'SYNTHETIC',status:'ACTIVE',created_at:stamp,updated_at:stamp});
  insert('farm_members',{id:'history-worker',farm_id:'history-farm',login_id:'history-worker',identity_provider:'SITES',identity_subject:'history-worker',role:'WORKER',status:'ACTIVE',created_at:stamp,updated_at:stamp,joined_at:stamp});
  const observation=await processScoutingObservation(repo,{farmId:'history-farm',houseId:'history-house',bedId:'history-bed',zoneId:'history-zone',sourceType:'THERMAL',
    observedAt:'2026-09-25T08:00:00Z',signals:{...baseSignals,hasMeaningfulNewEvidence:true}});
  const check=await recordScoutingFieldCheck(repo,{farmId:'history-farm',locationStateId:observation.locationStateId,memberId:'history-worker',
    evidenceCode:'NO_VISIBLE_EVIDENCE',checkedAt:'2026-09-25T08:10:00Z'});
  await correctScoutingFieldCheck(repo,{farmId:'history-farm',fieldCheckId:check.fieldCheckId,memberId:'history-worker',
    correctionKind:'REPLACE',replacementEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED',reasonCode:'MISCLICK',correctedAt:'2026-09-25T08:20:00Z'});
  await recordScoutingAction(repo,{farmId:'history-farm',locationStateId:observation.locationStateId,memberId:'history-worker',actionCode:'OBSERVE_ONLY',actionAt:'2026-09-25T08:30:00Z'});
  const {GET}=await import('../app/api/scouting-history/route');
  const request=(actor:string|null)=>new Request('https://synthetic.test/api/scouting-history?farmId=history-farm&locationStateId='+observation.locationStateId+'&limit=50',
    {headers:actor?{'oai-authenticated-user-id':actor}:{}});
  const tables=['scouting_location_states','scouting_cases','scouting_observations','scouting_field_checks','scouting_field_check_corrections','scouting_actions','scouting_case_events','scouting_alert_events'];
  const snapshot=()=>JSON.stringify(tables.map(t=>sqlite.prepare('SELECT * FROM '+t+' ORDER BY id').all()));
  const before=snapshot(),response=await GET(request('history-worker'));assert.equal(response.status,200);
  const data=await response.json(),entries=projectScoutingHistory(data,'history-farm',observation.locationStateId);
  assert.equal(entries.find(x=>x.kind==='fieldChecks')?.code,'NO_VISIBLE_EVIDENCE');
  assert.equal(entries.find(x=>x.kind==='corrections')?.replacementCode,'DIRECT_MITE_OR_EGG_CONFIRMED');
  assert.ok(entries.some(x=>x.kind==='observations'));assert.ok(entries.some(x=>x.kind==='actions'));assert.ok(entries.some(x=>x.kind==='alerts'));
  assert.equal(snapshot(),before,'history read must not rewrite source/projection/audit');
  assert.equal((await GET(request(null))).status,403);assert.equal((await GET(request('worker-h'))).status,403);
  sqlite.prepare("UPDATE farm_members SET status='INACTIVE' WHERE id='history-worker'").run();
  assert.equal((await GET(request('history-worker'))).status,403);assert.equal(snapshot(),before);
});

// Valid SQL FKs but deliberately inconsistent tenant ownership. Memory fixture only.
let tenantLocations: { a: string; b: string } | null = null;
async function tenantFixture() {
  if (tenantLocations) return tenantLocations;
  const locations: Record<string, string> = {};
  for (const s of ['a', 'b']) {
    insert('farms', { id: `tenant-farm-${s}`, code: `TF-${s}`, name: 'SYNTHETIC', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
    insert('houses', { id: `tenant-house-${s}`, farm_id: `tenant-farm-${s}`, code: 'H', name: 'SYNTHETIC', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
    insert('beds', { id: `tenant-bed-${s}`, house_id: `tenant-house-${s}`, code: 'B', name: 'SYNTHETIC', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
    insert('zones', { id: `tenant-zone-${s}`, bed_id: `tenant-bed-${s}`, code: 'Z', name: 'SYNTHETIC', status: 'ACTIVE', created_at: stamp, updated_at: stamp });
    locations[s] = (await repo.resolveLocation(`tenant-farm-${s}`, `tenant-house-${s}`, `tenant-bed-${s}`, `tenant-zone-${s}`, stamp)).id;
    insert('scouting_cases', { id: `tenant-case-${s}`, farm_id: `tenant-farm-${s}`, location_state_id: locations[s], issue_family: 'UNKNOWN', status: 'OPEN', opened_at: stamp, opened_reason: 'SYNTHETIC', created_at: stamp, updated_at: stamp });
    insert('scouting_observations', { id: `tenant-fk-observation-${s}`, farm_id: `tenant-farm-${s}`, location_state_id: locations[s], observed_at: stamp, source_type: 'MANUAL', created_at: stamp });
    insert('scouting_field_checks', { id: `tenant-fk-check-${s}`, farm_id: `tenant-farm-${s}`, location_state_id: locations[s], checked_at: stamp, primary_evidence_code: 'INCONCLUSIVE', created_at: stamp });
  }
  for (const [id, farm, role] of [['tenant-worker-a', 'tenant-farm-a', 'WORKER'], ['tenant-owner-a', 'tenant-farm-a', 'OWNER'], ['tenant-admin-a', 'tenant-farm-a', 'ADMIN'], ['tenant-owner-b', 'tenant-farm-b', 'OWNER']]) {
    insert('farm_members', { id, farm_id: farm, login_id: id, identity_provider: 'SITES', identity_subject: id, role, status: 'ACTIVE', created_at: stamp, updated_at: stamp, joined_at: stamp });
  }
  tenantLocations = { a: locations.a, b: locations.b }; return tenantLocations;
}
const tenantFamilies = [
  { key: 'observations', table: 'scouting_observations', time: 'observed_at', values: () => ({ source_type: 'MANUAL', policy_input_json: '{"synthetic":"RAW"}' }) },
  { key: 'fieldChecks', table: 'scouting_field_checks', time: 'checked_at', values: () => ({ primary_evidence_code: 'INCONCLUSIVE', note: 'SYNTHETIC_RAW_NOTE', secondary_evidence_json: '{"synthetic":"RAW"}' }) },
  { key: 'corrections', table: 'scouting_field_check_corrections', time: 'created_at', values: (s: string) => ({ field_check_id: `tenant-fk-check-${s}`, correction_kind: 'VOID', reason_code: 'MISCLICK', note: 'SYNTHETIC_RAW_NOTE' }) },
  { key: 'actions', table: 'scouting_actions', time: 'action_at', values: () => ({ action_code: 'OBSERVE_ONLY', detail_json: '{"synthetic":"RAW"}', note: 'SYNTHETIC_RAW_NOTE' }) },
  { key: 'alerts', table: 'scouting_alert_events', time: 'created_at', values: (s: string) => ({ observation_id: `tenant-fk-observation-${s}`, alert_decision: 'ISSUED', alert_reason: 'SYNTHETIC', policy_version: 'SYNTHETIC' }) },
  { key: 'caseEvents', table: 'scouting_case_events', time: 'created_at', values: (s: string) => ({ case_id: `tenant-case-${s}`, event_type: 'OPENED', detail_json: '{"synthetic":"RAW"}' }) },
];
for (const family of tenantFamilies) test(`tenant guard: ${family.key} rejects foreign rows before limit and preserves raw own rows`, async () => {
  const locations = await tenantFixture();
  for (const [label, farm, s, time] of [
    ['own-old', 'tenant-farm-a', 'a', '2026-11-05T10:00:00Z'],
    ['own-new', 'tenant-farm-a', 'a', '2026-11-05T10:01:00Z'],
    ['foreign-newest', 'tenant-farm-b', 'b', '2026-11-05T10:02:00Z'],
  ]) insert(family.table, { id: `tenant-${family.key}-${label}`, farm_id: farm, location_state_id: locations.a,
    ...family.values(s), created_at: time, [family.time]: time });
  assert.deepEqual(sqlite.prepare('PRAGMA foreign_key_check').all(), []);
  const snapshot = JSON.stringify(sqlite.prepare(`SELECT * FROM ${family.table} ORDER BY id`).all());
  const { GET } = await import('../app/api/scouting-history/route');
  const query = new URLSearchParams({ farmId: 'tenant-farm-a', locationStateId: locations.a, limit: '2' });
  const response = await GET(new Request('https://synthetic.test/api/scouting-history?' + query, { headers: { 'oai-authenticated-user-id': 'tenant-worker-a' } }));
  assert.equal(response.status, 200);
  const payload = await response.json() as Record<string, { id: string; farm_id: string }[]>;
  const rows = payload[family.key];
  assert.deepEqual(rows.map(row => row.id), [`tenant-${family.key}-own-new`, `tenant-${family.key}-own-old`]);
  assert.ok(rows.every(row => row.farm_id === 'tenant-farm-a'));
  const expected = rows.map(row => sqlite.prepare(`SELECT * FROM ${family.table} WHERE id=?`).get(row.id));
  assert.deepEqual(rows, JSON.parse(JSON.stringify(expected)), 'raw field shape must not be redacted');
  assert.equal(JSON.stringify(sqlite.prepare(`SELECT * FROM ${family.table} ORDER BY id`).all()), snapshot, 'read must not repair/delete stored evidence');
});

test('tenant guard: own roles stay allowed and foreign, anonymous, inactive or foreign-location requests stay denied', async () => {
  const locations = await tenantFixture();
  const { GET } = await import('../app/api/scouting-history/route');
  const request = (actor: string | null, location = locations.a) => new Request('https://synthetic.test/api/scouting-history?' + new URLSearchParams({ farmId: 'tenant-farm-a', locationStateId: location, limit: '2' }), { headers: actor ? { 'oai-authenticated-user-id': actor } : {} });
  for (const actor of ['tenant-worker-a', 'tenant-owner-a', 'tenant-admin-a']) {
    const response = await GET(request(actor)); assert.equal(response.status, 200);
    const data = await response.json() as Record<string, { farm_id: string }[]>;
    for (const family of tenantFamilies) assert.ok(data[family.key].every(row => row.farm_id === 'tenant-farm-a'));
  }
  assert.equal((await GET(request(null))).status, 403);
  assert.equal((await GET(request('tenant-owner-b'))).status, 403);
  assert.equal((await GET(request('tenant-worker-a', locations.b))).status, 404);
  sqlite.exec("UPDATE farm_members SET status='INACTIVE' WHERE id='tenant-worker-a'");
  assert.equal((await GET(request('tenant-worker-a'))).status, 403);
});
