import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider } from './support/test-identity-provider';
import { executeScoutingIntent, normalizeScoutingIntent } from '../app/features/pests/application/scouting-intent';
import { recordScoutingFieldCheck, correctScoutingFieldCheck, recordScoutingAction, resolveScoutingCase } from '../app/features/pests/application/scouting-service';
import { ScoutingRepository } from '../app/features/pests/infrastructure/scouting-repository';
const handlers = {
  CHECK: (await import('../app/api/scouting-field-checks/route')).POST,
  CORRECTION: (await import('../app/api/scouting-field-check-corrections/route')).POST,
  ACTION: (await import('../app/api/scouting-actions/route')).POST,
  RESOLVE: (await import('../app/api/scouting-resolve/route')).POST,
};
type Kind = keyof typeof handlers;
function activate(f: ReturnType<typeof scoutingIntentFixture>) {
  (globalThis as unknown as { nongtoriTestEnv: unknown }).nongtoriTestEnv = f.env;
}
function request(kind: Kind, body: object, key = crypto.randomUUID(), actor: 'worker-a' | 'owner-a' | 'owner-b' | null = 'worker-a') {
  return testIdentityProvider.requestAs(actor, `/api/synthetic-${kind}`, {
    method: 'POST', headers: { 'content-type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify(body),
  });
}
function count(f: ReturnType<typeof scoutingIntentFixture>, table: string) { return (f.sqlite.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as { n: number }).n; }
async function checked(f: ReturnType<typeof scoutingIntentFixture>) {
  return recordScoutingFieldCheck(new ScoutingRepository(f.db), { farmId: 'farm-a', locationStateId: 'loc',
    memberId: 'worker-a', evidenceCode: 'NO_VISIBLE_EVIDENCE', checkedAt: '2026-11-02T00:00:00Z' });
}
async function bodyFor(kind: Kind, f: ReturnType<typeof scoutingIntentFixture>) {
  if (kind === 'CHECK') return { farmId: 'farm-a', locationStateId: 'loc', evidenceCode: 'NO_VISIBLE_EVIDENCE' };
  if (kind === 'CORRECTION') return { farmId: 'farm-a', fieldCheckId: (await checked(f)).fieldCheckId,
    correctionKind: 'REPLACE', replacementEvidenceCode: 'DIRECT_MITE_OR_EGG_CONFIRMED', reasonCode: 'MISCLICK' };
  if (kind === 'ACTION') return { farmId: 'farm-a', locationStateId: 'loc', actionCode: 'TREATMENT_APPLIED' };
  return { farmId: 'farm-a', locationStateId: 'loc', reasonCode: 'TREATMENT_COMPLETED' };
}
test('four actual keyed POST handlers replay original results and reject edited payload without extra writes', async () => {
  for (const kind of Object.keys(handlers) as Kind[]) {
    const f = scoutingIntentFixture(); activate(f);
    try {
      const body = await bodyFor(kind, f), key = crypto.randomUUID();
      const table = { CHECK: 'scouting_field_checks', CORRECTION: 'scouting_field_check_corrections', ACTION: 'scouting_actions', RESOLVE: 'scouting_case_events' }[kind];
      const domainBefore = count(f,table), eventsBefore = count(f,'scouting_case_events');
      const versionBefore = (f.sqlite.prepare("SELECT state_version FROM scouting_location_states WHERE id='loc'").get() as {state_version:number}).state_version;
      const rawBefore = f.sqlite.prepare('SELECT * FROM scouting_field_checks ORDER BY id').all();
      const first = await handlers[kind](request(kind, body, key));
      assert.equal(first.status, kind === 'RESOLVE' ? 200 : 201, await first.clone().text());
      assert.equal(count(f,table),domainBefore+1,`${kind} real domain effect`);
      assert.equal(count(f,'scouting_case_events'),eventsBefore+(kind==='CORRECTION'||kind==='RESOLVE'?1:0));
      assert.equal((f.sqlite.prepare("SELECT state_version FROM scouting_location_states WHERE id='loc'").get() as {state_version:number}).state_version,versionBefore+1);
      if(kind==='CORRECTION')assert.deepEqual(f.sqlite.prepare('SELECT * FROM scouting_field_checks ORDER BY id').all(),rawBefore);
      const result = await first.json(), before = f.snapshot();
      const replay = await handlers[kind](request(kind, body, key));
      assert.equal(replay.status, first.status); assert.deepEqual(await replay.json(), result);
      assert.equal((await handlers[kind](request(kind, { ...body, note: 'different' }, key))).status, 409);
      assert.deepEqual(f.snapshot(), before);
      assert.equal(count(f, 'scouting_operation_receipts'), 1); assert.equal(count(f, 'scouting_operation_guards'), 0);
      assert.equal(f.observedSql.some(sql => /CREATE |ALTER |DROP /i.test(sql)), false, 'handler must not run bootstrap DDL');
    } finally { f.sqlite.close(); }
  }
});
test('default off, missing quota, absent schema and invalid key fail closed without DDL or mutation', async () => {
  const body = { farmId: 'farm-a', locationStateId: 'loc', evidenceCode: 'NO_VISIBLE_EVIDENCE' };
  for (const mode of ['off','quota','schema','key']) {
    const f = scoutingIntentFixture(mode !== 'schema'); activate(f);
    try {
      if (mode === 'off') f.env.SCOUTING_MUTATION_IDEMPOTENCY = '';
      if (mode === 'quota') f.env.SCOUTING_RECEIPT_FARM_LIMIT = '';
      const before = f.snapshot();
      const r = await handlers.CHECK(request('CHECK', body, mode === 'key' ? '' : crypto.randomUUID()));
      assert.equal(r.status, mode === 'key' ? 422 : 503); assert.deepEqual(f.snapshot(), before);
      assert.equal(f.observedSql.some(sql => /CREATE |ALTER |DROP |INSERT |UPDATE |DELETE /i.test(sql)), false);
    } finally { f.sqlite.close(); }
  }
});
test('current identity, farm ownership, revocation and member-scoped receipts remain authoritative', async () => {
  const f = scoutingIntentFixture(); activate(f);
  try {
    const body = await bodyFor('CHECK', f), key = crypto.randomUUID();
    assert.equal((await handlers.CHECK(request('CHECK', body, key))).status, 201);
    const before = f.snapshot();
    for (const actor of [null,'owner-b'] as const) assert.equal((await handlers.CHECK(request('CHECK', body, key, actor))).status, 403);
    assert.equal((await handlers.CHECK(request('CHECK', { ...body, farmId: 'farm-b' }, key, 'owner-b'))).status, 400);
    f.sqlite.exec("UPDATE farm_members SET status='INACTIVE' WHERE id='worker-a'");
    assert.equal((await handlers.CHECK(request('CHECK', body, key))).status, 403);
    assert.deepEqual(f.snapshot(), before);
    assert.equal((await handlers.CHECK(request('CHECK', body, key, 'owner-a'))).status, 201);
    assert.equal(count(f,'scouting_operation_receipts'),2,'another member cannot obtain original receipt');
  } finally { f.sqlite.close(); }
});
test('each batch write failure rolls receipt, domain, projection and existing events back for all four operations', async () => {
  for (const kind of Object.keys(handlers) as Kind[]) {
    // Each path has at least these first five writes, including claim/quota/domain/projection.
    for (let index = 0; index < (kind === 'CHECK' ? 6 : kind === 'CORRECTION' ? 7 : kind === 'ACTION' ? 6 : 6); index++) {
      const f = scoutingIntentFixture(); activate(f);
      try {
        const body = await bodyFor(kind,f), before=f.snapshot(); f.failAt(index);
        const r=await handlers[kind](request(kind,body));
        assert.equal(r.status,503,`${kind} index${index}`);assert.deepEqual(f.snapshot(),before);
      } finally { f.sqlite.close(); }
    }
  }
});
test('ambiguous batch acknowledgement recovers committed response and a lost client response replays once', async () => {
  const f=scoutingIntentFixture();activate(f);
  try {
    const body=await bodyFor('CHECK',f),key=crypto.randomUUID();f.loseCommitResponse();
    const first=await handlers.CHECK(request('CHECK',body,key));assert.equal(first.status,201);
    const result=await first.json(),before=f.snapshot(); // client now discards result
    const retry=await handlers.CHECK(request('CHECK',body,key));assert.deepEqual(await retry.json(),result);
    assert.deepEqual(f.snapshot(),before);assert.equal(count(f,'scouting_field_checks'),1);
  } finally { f.sqlite.close(); }
});
test('farm/member row quota rejects new intent but keeps existing replay available', async () => {
  for (const limit of ['SCOUTING_RECEIPT_FARM_LIMIT','SCOUTING_RECEIPT_MEMBER_LIMIT'] as const) {
    const f=scoutingIntentFixture();activate(f);f.env[limit]='1';
    try {
      const body=await bodyFor('ACTION',f),key=crypto.randomUUID();
      const first=await handlers.ACTION(request('ACTION',body,key));assert.equal(first.status,201);
      const before=f.snapshot();const r=await handlers.ACTION(request('ACTION',body));
      assert.equal(r.status,429,await r.clone().text());assert.deepEqual(f.snapshot(),before);
      assert.equal((await handlers.ACTION(request('ACTION',body,key))).status,201);
    } finally { f.sqlite.close(); }
  }
});
test('new-key historical correction and action retain existing case and event semantics', async () => {
  for (const kind of ['CORRECTION','ACTION','RESOLVE','CHECK'] as const) {
    const a=scoutingIntentFixture(),b=scoutingIntentFixture();
    try {
      const abody=await bodyFor(kind,a),bbody=await bodyFor(kind,b);
      if(kind==='CORRECTION')for(const f of [a,b])f.sqlite.exec("UPDATE scouting_cases SET status='RESOLVED'; UPDATE scouting_location_states SET active_case_id=NULL,current_state='RESOLVED'");
      const repo=new ScoutingRepository(a.db);const p=abody as Record<string,unknown>;
      if(kind==='CORRECTION')await correctScoutingFieldCheck(repo,{farmId:'farm-a',memberId:'worker-a',fieldCheckId:p.fieldCheckId as string,correctionKind:'REPLACE',replacementEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED',reasonCode:'MISCLICK',correctedAt:'T'});
      else if(kind==='ACTION')await recordScoutingAction(repo,{farmId:'farm-a',memberId:'worker-a',locationStateId:'loc',actionCode:'TREATMENT_APPLIED',actionAt:'T'});
      else if(kind==='CHECK')await recordScoutingFieldCheck(repo,{farmId:'farm-a',memberId:'worker-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE',checkedAt:'T'});
      else await resolveScoutingCase(repo,{farmId:'farm-a',memberId:'worker-a',locationStateId:'loc',reasonCode:'TREATMENT_COMPLETED',resolvedAt:'T'});
      await executeScoutingIntent(b.db,'worker-a',crypto.randomUUID(),normalizeScoutingIntent(kind,bbody),{farm:10,member:10});
      for(const f of [a,b])assert.equal(count(f,'scouting_case_events'),kind==='CORRECTION'||kind==='RESOLVE'?1:0);
      assert.equal((a.sqlite.prepare('SELECT current_state FROM scouting_location_states').get() as {current_state:string}).current_state,
        (b.sqlite.prepare('SELECT current_state FROM scouting_location_states').get() as {current_state:string}).current_state);
    } finally {a.sqlite.close();b.sqlite.close();}
  }
});
test('bounded keyed payload and unchanged automatic DDL sources', async () => {
  const f=scoutingIntentFixture();activate(f);
  try {
    const body=await bodyFor('ACTION',f),before=f.snapshot();
    assert.equal((await handlers.ACTION(request('ACTION',{...body,detail:'x'.repeat(17000)}))).status,422);
    assert.deepEqual(f.snapshot(),before);
    for(const file of ['db/index.ts','db/scouting-runtime.ts'])assert.equal(readFileSync(file,'utf8').includes('scouting_operation_receipts'),false);
  } finally {f.sqlite.close();}
});
test('concurrent handler intents serialize atomic claims and quotas in the synthetic adapter', async () => {
  for(const sameKey of [true,false]) {
    const f=scoutingIntentFixture();activate(f);f.env.SCOUTING_RECEIPT_FARM_LIMIT='1';
    try {
      const body=await bodyFor('ACTION',f),key=crypto.randomUUID();
      const results=await Promise.all([handlers.ACTION(request('ACTION',body,key)),
        handlers.ACTION(request('ACTION',body,sameKey?key:crypto.randomUUID()))]);
      assert.deepEqual(results.map(r=>r.status).sort(),sameKey?[201,201]:[201,429]);
      if(sameKey)assert.deepEqual(await results[0].json(),await results[1].json());
      assert.equal(count(f,'scouting_actions'),1);assert.equal(count(f,'scouting_operation_receipts'),1);
    }finally{f.sqlite.close();}
  }
});
test('planning read failure stays uncertain while known invalid evidence is a definite rejection',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try {
    const body=await bodyFor('CHECK',f),before=f.snapshot();
    f.failReadContaining('SELECT * FROM scouting_observations');
    const failed=await handlers.CHECK(request('CHECK',body));
    assert.equal(failed.status,503);assert.equal((await failed.json() as {code:string}).code,'MUTATION_RESULT_UNCERTAIN');
    assert.deepEqual(f.snapshot(),before);
    const invalid=await handlers.CHECK(request('CHECK',{...body,evidenceCode:'NOT_EVIDENCE'}));
    assert.equal(invalid.status,400);assert.equal((await invalid.json() as {code:string}).code,'INVALID_MUTATION');
    assert.deepEqual(f.snapshot(),before);
  }finally{f.sqlite.close();}
});
