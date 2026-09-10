import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { PestRepository } from '../app/features/pests/infrastructure/pest-repository';
import { loadPestDashboard } from '../app/features/pests/application/pest-service';
import { pestTargets } from '../app/features/pests/domain/catalog';

// In-memory, isolated fixture only: execute production SQL, no external farm data.
const sqlite = new DatabaseSync(':memory:');
sqlite.exec('PRAGMA foreign_keys = ON');
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name < '0014').sort()) sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
function prepare(sql: string) {
  const statement = () => sqlite.prepare(sql);
  let args: (string | number | null)[] = [];
  return {
    bind(...values: (string | number | null)[]) { args = values; return this; },
    async all() { return { results: statement().all(...args), success: true, meta: {} }; },
    async first() { return statement().get(...args) ?? null; },
    async run() { const result = statement().run(...args); return { success: true, meta: { changes: Number(result.changes) } }; },
  };
}
const db = { prepare, async batch(statements: ReturnType<typeof prepare>[]) {
  sqlite.exec('BEGIN');
  try { const results = []; for (const statement of statements) results.push(await statement.run()); sqlite.exec('COMMIT'); return results; }
  catch (error) { sqlite.exec('ROLLBACK'); throw error; }
} } as unknown as D1Database;
const objects = new Map<string, unknown>();
(globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = {
  DB: db, FILES: { async put(key: string, body: unknown) { objects.set(key, body); }, async delete(key: string) { objects.delete(key); } },
};
const { ensureSchema } = await import('../db');
await ensureSchema();
// Retained migration 0014 depends on joined_at from the legacy runtime bootstrap.
for (const file of readdirSync('drizzle').filter((name) => name.endsWith('.sql') && name >= '0014').sort()) sqlite.exec(readFileSync(`drizzle/${file}`, 'utf8'));
const notes = await import('../app/api/record-notes/route');
const oldNotes = await import('../app/api/mite-record-notes/route');
const capture = await import('../app/api/pest-capture/route');
const reviews = await import('../app/api/alert-reviews/route');
const dashboard = await import('../app/api/farmer-dashboard/route');
const history = await import('../app/api/operation-history/route');
const stamp = '2026-09-08T08:00:00.000Z';
function insert(table: string, values: Record<string, string | number | null>) {
  const rows = sqlite.prepare(`PRAGMA table_info(${table})`).all() as { name: string; notnull: number; dflt_value: unknown; type: string }[];
  for (const column of rows) if (!(column.name in values) && column.notnull && column.dflt_value === null) values[column.name] = column.type.toUpperCase().includes('INT') ? 0 : 'TEST_ONLY';
  const keys = Object.keys(values);
  sqlite.prepare(`INSERT INTO ${table} (${keys.join(',')}) VALUES (${keys.map(() => '?').join(',')})`).run(...Object.values(values));
}
for (const farmId of ['test-a', 'test-b']) insert('farms', { id: farmId, code: farmId, name: farmId, status: 'ACTIVE', created_at: stamp, updated_at: stamp });
for (const [id, role, farm] of [['owner', 'OWNER', 'test-a'], ['worker', 'WORKER', 'test-a'], ['outsider', 'OWNER', 'test-b']]) insert('farm_members', { id, farm_id: farm, login_id: id, role, identity_provider: 'SITES', identity_subject: id, status: 'ACTIVE', display_name: id, created_at: stamp, updated_at: stamp, joined_at: stamp });
function session(id: string, farm = 'test-a') { insert('capture_sessions', { id, farm_id: farm, capture_mode: 'VIDEO', source_type: 'VIDEO_IMPORT', processing_status: 'UPLOADED_AWAITING_MODEL', started_at: stamp, created_at: stamp }); }
session('pending'); session('pending-other'); session('foreign', 'test-b'); session('analyzed');
insert('video_assets', { id: 'video', capture_session_id: 'analyzed', modality: 'RGB_VIDEO', processing_status: 'COMPLETED', created_at: stamp });
let frameIndex = 0;
function prediction(id: string, label: string, task: string, track = id, confidence = 0.8) {
  if (!sqlite.prepare('SELECT id FROM inference_runs WHERE id = ?').get(task)) insert('inference_runs', { id: task, capture_session_id: 'analyzed', task, model_version: 'TEST_ONLY', status: 'COMPLETED', started_at: stamp, created_at: stamp });
  insert('frames', { id: `${id}-frame`, video_asset_id: 'video', capture_session_id: 'analyzed', frame_index: ++frameIndex, timestamp_ms: frameIndex * 1000, processing_status: 'COMPLETED', created_at: stamp });
  insert('frame_predictions', { id, inference_run_id: task, frame_id: `${id}-frame`, track_id: track, class_label: label, confidence, decision_status: 'REVIEW_REQUIRED', created_at: stamp });
}
prediction('mite', '응애의심', 'MITE_DETECTION', 'leaf');
prediction('mite-duplicate', 'MITE_SUSPECTED', 'MITE_DETECTION', 'leaf', 0.7);
prediction('mildew', 'POWDERY_MILDEW', 'DISEASE_DETECTION');
prediction('aphid', 'APHID', 'PEST_DETECTION');
prediction('other', 'PEST_UNLISTED', 'PEST_DETECTION');
prediction('fruit', 'RIPE_FRUIT', 'QUALITY');
function request(path: string, actor = 'owner', method = 'GET', body?: object) {
  return new Request(`https://nongtori.test/api/${path}`, { method, headers: { 'oai-authenticated-user-id': actor, ...(body ? { 'content-type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
}
const repo = new PestRepository(db);

test('multiple pests have independent counts, filtering, deduplication and pagination', async () => {
  const all = await loadPestDashboard(repo, 'test-a', '', 'OPEN', 1);
  assert.equal(all.totalOpen, 4); assert.equal(all.rows.length, 4);
  assert.equal(all.breakdown.find((x) => x.code === 'MITE')?.openCount, 1);
  const filtered = await loadPestDashboard(repo, 'test-a', 'POWDERY_MILDEW', 'OPEN', 999);
  assert.equal(filtered.pagination.page, 1); assert.deepEqual(filtered.rows.map((x) => x.id), ['mildew']);
  assert.equal((await loadPestDashboard(repo, 'test-b', '', 'OPEN', 1)).totalOpen, 0);
  await assert.rejects(loadPestDashboard(repo, 'test-a', "'; DROP TABLE farms;", 'OPEN', 1));
  assert.equal((await loadPestDashboard(repo, 'test-a', 'GRAY_MOLD', 'OPEN', 1)).pagination.total, 0);
  const response = await dashboard.GET(request('farmer-dashboard?farmId=test-a&pestCode=APHID'));
  assert.equal(response.status, 200); const json = await response.json() as { summary: { alertCount: number }; alerts: { pest_code: string }[]; alertPagination: { total: number } };
  assert.equal(json.summary.alertCount, 4); assert.equal(json.alerts[0].pest_code, 'APHID');
  assert.equal(json.alertPagination.total, 1);
});

test('generic review resolves the correct pest; legacy mite verdicts cannot resolve another disease', async () => {
  const base = { farmId: 'test-a', predictionId: 'mildew', verdict: 'TARGET_CONFIRMED' };
  assert.equal((await reviews.POST(request('alert-reviews', 'worker', 'POST', base))).status, 201);
  const done = await loadPestDashboard(repo, 'test-a', 'POWDERY_MILDEW', 'DONE', 1);
  assert.equal(done.rows.length, 1); assert.equal(done.rows[0].review_verdict, 'TARGET_CONFIRMED');
  assert.equal((await reviews.POST(request('alert-reviews', 'worker', 'POST', { ...base, verdict: 'MITE_CONFIRMED' }))).status, 400);
  assert.equal((await reviews.POST(request('alert-reviews', 'outsider', 'POST', base))).status, 403);
  assert.equal((await reviews.GET(request('alert-reviews?farmId=test-a&predictionId=mildew', 'worker'))).status, 200);
});

test('owner and worker exchange durable replies on pending records; membership, author and target boundaries hold', async () => {
  const body = { farmId: 'test-a', sessionId: 'pending', content: '사진 확인 부탁드립니다.', languageHint: 'ko' };
  const created = await notes.POST(request('record-notes', 'owner', 'POST', body)); assert.equal(created.status, 201);
  const { id } = await created.json() as { id: string };
  const reply = await notes.POST(request('record-notes', 'worker', 'POST', { ...body, content: '현장에서 다시 확인하겠습니다.', parentNoteId: id })); assert.equal(reply.status, 201);
  const { rows } = await (await notes.GET(request('record-notes?farmId=test-a&sessionId=pending', 'worker'))).json() as { rows: { parent_note_id: string; author_role_snapshot: string }[] };
  assert.equal(rows.length, 2); assert.equal(rows[1].parent_note_id, id);
  assert.deepEqual(rows.map((x: { author_role_snapshot: string }) => x.author_role_snapshot), ['OWNER', 'WORKER']);
  assert.equal((await notes.PATCH(request('record-notes', 'worker', 'PATCH', { ...body, noteId: id, content: 'overwrite' }))).status, 403);
  assert.equal((await notes.PATCH(request('record-notes', 'owner', 'PATCH', { ...body, noteId: id, content: '사진 확인해 주세요.' }))).status, 200);
  assert.equal((await notes.POST(request('record-notes', 'worker', 'POST', { ...body, sessionId: 'pending-other', parentNoteId: id }))).status, 422);
  assert.equal((await notes.GET(request('record-notes?farmId=test-a&sessionId=foreign', 'worker'))).status, 403);
  assert.equal((await notes.POST(request('record-notes', 'outsider', 'POST', body))).status, 403);
  assert.equal((await oldNotes.GET(request('mite-record-notes?farmId=test-a&sessionId=pending', 'worker'))).status, 200);
  const list = await (await history.GET(request('operation-history?farmId=test-a'))).json() as { rows: { id: string; note_count: number }[] };
  assert.equal(list.rows.find((row: { id: string }) => row.id === 'pending')?.note_count, 2);
});

test('comments accept fruit and non-mite predictions, and forbid cross-frame replies', async () => {
  const body = { farmId: 'test-a', predictionId: 'fruit', content: '품질 확인했습니다.', languageHint: 'ko' };
  const created = await notes.POST(request('record-notes', 'worker', 'POST', body)); assert.equal(created.status, 201);
  const { id } = await created.json() as { id: string };
  assert.equal((await notes.POST(request('record-notes', 'owner', 'POST', { ...body, predictionId: 'mildew', content: '다시 확인합니다.' }))).status, 201);
  assert.equal((await notes.POST(request('record-notes', 'owner', 'POST', { ...body, predictionId: 'mildew', parentNoteId: id }))).status, 422);
  const frames = await notes.GET(request('record-notes?farmId=test-a&sessionId=analyzed&mode=frames'));
  assert.equal(frames.status, 200); assert.equal((await frames.json() as { frames: unknown[] }).frames.length, 6);
});

test('every catalog target can be captured without fabricating inference output; unauthorized uploads fail', async () => {
  for (const target of pestTargets) {
    const body = new FormData(); body.set('farmId', 'test-a'); body.set('pestCode', target.code);
    body.set('rgbImage', new File(['TEST_ONLY'], 'fixture.png', { type: 'image/png' }));
    const response = await capture.POST(new Request('https://nongtori.test/api/pest-capture', { method: 'POST', headers: { 'oai-authenticated-user-id': 'worker' }, body }));
    assert.equal(response.status, 201, await response.clone().text());
    const { sessionId } = await response.json() as { sessionId: string };
    const stored = sqlite.prepare('SELECT pest_code, processing_status FROM capture_sessions WHERE id = ?').get(sessionId);
    assert.equal(stored?.pest_code, target.code); assert.equal(stored?.processing_status, 'UPLOADED_AWAITING_MODEL');
    assert.equal(sqlite.prepare('SELECT COUNT(*) AS count FROM inference_runs WHERE capture_session_id = ?').get(sessionId)?.count, 0);
  }
  const body = new FormData(); body.set('farmId', 'test-a'); body.set('pestCode', 'APHID'); body.set('rgbImage', new File(['TEST_ONLY'], 'fixture.png', { type: 'image/png' }));
  assert.equal((await capture.POST(new Request('https://nongtori.test/api/pest-capture', { method: 'POST', headers: { 'oai-authenticated-user-id': 'outsider' }, body }))).status, 403);
});
