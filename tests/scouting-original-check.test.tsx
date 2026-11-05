// Synthetic in-memory binding and injected fetch only. No bootstrap or external IO.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { GET } from '../app/api/scouting-original-check/route';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
import { ScoutingOriginalReader, type OriginalState } from '../app/features/pests/presentation/scouting-original-reader';
import { ScoutingHistoryPanel } from '../app/features/pests/presentation/ScoutingHistory';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider, type TestIdentitySubject } from './support/test-identity-provider';

function fixture() {
  const f = scoutingIntentFixture(false);
  (globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = { DB: f.db };
  for (let i = 0; i < 51; i++) f.sqlite.prepare(`INSERT INTO scouting_field_checks
    (id,farm_id,location_state_id,checked_at,primary_evidence_code,note,created_at)
    VALUES(?, 'farm-a','loc',?,'INCONCLUSIVE','PRIVATE_NOTE',?)`)
    .run(`check-${i}`, `2026-01-01T00:00:${String(i).padStart(2,'0')}Z`, 'T');
  return f;
}
const request = (actor: TestIdentitySubject | null = 'worker-a', farmId = 'farm-a', locationStateId = 'loc', fieldCheckId = 'check-0') =>
  testIdentityProvider.requestAs(actor, `/api/scouting-original-check?${new URLSearchParams({ farmId, locationStateId, fieldCheckId })}`);
const original = (overrides = {}) => ({ original: { id: 'check-0', farm_id: 'farm-a', location_state_id: 'loc', primary_evidence_code: 'INCONCLUSIVE', checked_at: '2026-01-01T00:00:00Z', ...overrides } });

test('real GET reads an original outside latest 50, minimal projection, no bootstrap or writes', async () => {
  const f = fixture();
  try {
    const history = await new ScoutingRepository(f.db).locationHistory('farm-a','loc',50);
    assert.ok(!history!.fieldChecks.some((row: Record<string, unknown>) => row.id === 'check-0'));
    const before = f.snapshot(); f.observedSql.length = 0;
    for (const actor of ['worker-a','owner-a'] as const) {
      const r = await GET(request(actor)); assert.equal(r.status,200);
      assert.equal(r.headers.get('cache-control'),'no-store');
      assert.deepEqual(await r.json(),original());
    }
    assert.deepEqual(f.snapshot(),before);
    assert.ok(f.observedSql.length > 0);
    assert.ok(f.observedSql.every(sql => /^\s*SELECT\b/i.test(sql)));
  } finally { f.sqlite.close(); }
});

test('real GET preserves membership, farm, location, target, absence and inactive boundaries', async () => {
  const f = fixture();
  try {
    for (const [req, expected] of [
      [request(null),403], [request('owner-b'),403],
      [request('owner-b','farm-b'),404], [request('worker-a','farm-a','wrong'),404],
      [request('worker-a','farm-a','loc','missing'),404], [request('worker-a','','loc'),422],
      [request('worker-a','farm-a','loc','x'.repeat(101)),422],
    ] as const) {
      const r = await GET(req); assert.equal(r.status,expected);
      assert.equal(r.headers.get('cache-control'),'no-store');
      assert.ok(!JSON.stringify(await r.json()).includes('PRIVATE_NOTE'));
    }
    f.sqlite.exec("UPDATE farm_members SET status='INACTIVE' WHERE id='worker-a'");
    assert.equal((await GET(request())).status,403);
    // Deliberately inconsistent synthetic row: check claims farm-a but location belongs to farm-b.
    f.sqlite.exec("UPDATE scouting_location_states SET farm_id='farm-b' WHERE id='loc'");
    assert.equal((await GET(request('owner-a'))).status,404);
  } finally { f.sqlite.close(); }
});

test('read failure is sanitized and does not bootstrap missing schema', async () => {
  const f = fixture();
  try {
    f.sqlite.exec('DROP TABLE scouting_field_check_corrections; DROP TABLE scouting_field_checks');
    f.observedSql.length = 0;
    const r = await GET(request()); assert.equal(r.status,503);
    assert.deepEqual(await r.json(),{ error:'ORIGINAL_CHECK_UNAVAILABLE' });
    assert.ok(f.observedSql.every(sql => /^\s*SELECT\b/i.test(sql)));
  } finally { f.sqlite.close(); }
});

test('reader coalesces clicks, projects only safe fields and discards late context/unmount responses', async () => {
  const pending: ((r: Response) => void)[] = [], urls: string[] = [];
  const reader = new ScoutingOriginalReader(async (url, init) => {
    urls.push(String(url)); assert.equal(init?.method,'GET'); assert.equal(init?.cache,'no-store');
    return new Promise<Response>(resolve => pending.push(resolve));
  });
  const states: OriginalState[] = [];
  const a = reader.load('farm-a','loc','check-0',s => states.push(s));
  await reader.load('farm-a','loc','check-0',s => states.push(s));
  assert.equal(urls.length,1);
  reader.invalidate(); // same action as effect cleanup on context switch/unmount
  const b = reader.load('farm-a','loc-2','check-1',s => states.push(s));
  pending[0](Response.json(original())); await a;
  assert.equal(states.filter(s => s.status === 'ready').length,0);
  pending[1](Response.json(original({ id:'check-1',location_state_id:'loc-2', note:'SECRET', checker_member_id:'SECRET' })));
  await b;
  assert.equal(states.at(-1)?.entry?.id,'check-1');
  assert.ok(!JSON.stringify(states).includes('SECRET'));
  const c = reader.load('farm-a','loc','check-0',s => states.push(s));
  reader.invalidate(); const n = states.length; pending[2](Response.json(original())); await c;
  assert.equal(states.length,n);
  const d = reader.load('farm-a','loc','check-0',s => states.push(s));
  reader.invalidate(); const afterUnmount = states.length;
  pending[3](new Response('',{status:503})); await d;
  assert.equal(states.length,afterUnmount);
});

test('reader distinguishes absent/denied/error, clears old data and rejects scope mismatch', async () => {
  let response = Response.json(original());
  const reader = new ScoutingOriginalReader(async () => response);
  const states: OriginalState[] = [];
  const load = () => reader.load('farm-a','loc','check-0',s => states.push(s));
  await load(); assert.equal(states.at(-1)?.status,'ready');
  for (const [status, expected] of [[404,'missing'],[403,'denied'],[503,'error']] as const) {
    response = new Response('',{status}); await load();
    assert.equal(states.at(-1)?.status,expected); assert.equal(states.at(-1)?.entry,null);
  }
  response = Response.json(original({farm_id:'farm-b'})); await load();
  assert.equal(states.at(-1)?.status,'error'); assert.equal(states.at(-1)?.entry,null);
});

test('out-of-window correction exposes explicit original action only in current ready context', () => {
  const state = { scope:'scope',status:'ready' as const,entries:[{kind:'corrections' as const,id:'correction',at:null,code:'VOID',originalCheckId:'check-0',replacementCode:null}] };
  const html = renderToStaticMarkup(<ScoutingHistoryPanel state={state} language="ko" onRetry={() => {}} farmId="farm-a" locationId="loc" />);
  assert.ok(html.includes('원본 단건 조회')); assert.ok(html.includes('입력 무효'));
  assert.ok(!html.includes('원본 기록 · 정정 적용 전'));
  const stale = renderToStaticMarkup(<ScoutingHistoryPanel state={{...state,status:'stale'}} language="ko" onRetry={() => {}} farmId="farm-a" locationId="loc" />);
  assert.ok(!stale.includes('원본 단건 조회'));
});
