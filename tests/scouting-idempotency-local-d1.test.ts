// Explicit local-emulator integration only; not included in automatic workflow.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
import { realpathSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider } from './support/test-identity-provider';
const requireWrangler=createRequire(realpathSync('node_modules/wrangler/package.json'));
const { Miniflare } = requireWrangler('miniflare');
const {POST}=await import('../app/api/scouting-field-checks/route');
const routes={
  CHECK:POST,
  CORRECTION:(await import('../app/api/scouting-field-check-corrections/route')).POST,
  ACTION:(await import('../app/api/scouting-actions/route')).POST,
  RESOLVE:(await import('../app/api/scouting-resolve/route')).POST,
};
type Kind=keyof typeof routes;
async function seedLocalBinding(db:D1Database,f:ReturnType<typeof scoutingIntentFixture>){
  const objects=f.sqlite.prepare("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END,rowid").all() as {type:string;name:string;sql:string}[];
  await db.batch(objects.map(o=>db.prepare(o.sql)));
  for(const o of objects.filter(o=>o.type==='table'))for(const row of f.sqlite.prepare(`SELECT * FROM ${o.name}`).all()){
    const keys=Object.keys(row);
    await db.prepare(`INSERT INTO ${o.name}(${keys.join(',')}) VALUES(${keys.map(()=>'?').join(',')})`).bind(...Object.values(row)).run();
  }
}
async function localHarness(){
  let outbound=0;
  const mf=new Miniflare({modules:true,script:'export default {fetch(){return new Response("SYNTHETIC")}}',
    compatibilityDate:'2026-05-15',host:'127.0.0.1',port:0,cf:false,d1Databases:['SYNTHETIC_DB'],
    d1Persist:mkdtempSync(path.join(tmpdir(),'nongtori-intent-d1-')),outboundService:()=>{outbound++;throw Error('OUTBOUND_DISABLED');}});
  const f=scoutingIntentFixture();
  try{
    const db=await mf.getD1Database('SYNTHETIC_DB') as D1Database;
    await seedLocalBinding(db,f);
    const env={...f.env,DB:db};
    (globalThis as unknown as {nongtoriTestEnv:unknown}).nongtoriTestEnv=env;
    const snapshot=async()=>{
      const out:Record<string,unknown>={};
      for(const table of ['scouting_field_checks','scouting_field_check_corrections','scouting_actions','scouting_cases',
        'scouting_location_states','scouting_case_events','scouting_operation_receipts','scouting_operation_guards'])
        out[table]=(await db.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all()).results;
      return out;
    };
    const call=(kind:Kind,body:object,key:string,actor:'worker-a'|'owner-b'|null='worker-a')=>routes[kind](testIdentityProvider.requestAs(actor,`/api/synthetic-${kind}`,{
      method:'POST',headers:{'content-type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)}));
    return {db,env,call,snapshot,async close(){f.sqlite.close();await mf.dispose();assert.equal(outbound,0);}};
  }catch(error){f.sqlite.close();await mf.dispose();throw error;}
}
test('real keyed handler plan commits and rolls back through official local D1 binding.batch',async()=>{
  let outbound=0;
  const state=mkdtempSync(path.join(tmpdir(),'nongtori-intent-d1-'));
  console.info('Synthetic local D1 state:',state);
  const mf=new Miniflare({modules:true,script:'export default {fetch(){return new Response("SYNTHETIC")}}',
    compatibilityDate:'2026-05-15',host:'127.0.0.1',port:0,cf:false,d1Databases:['SYNTHETIC_DB'],
    d1Persist:state,outboundService:()=>{outbound++;throw Error('OUTBOUND_DISABLED');}});
  const f=scoutingIntentFixture();
  try {
    const db=await mf.getD1Database('SYNTHETIC_DB') as D1Database;
    // Copy ONLY this test's fresh synthetic schema/rows. No bootstrap or existing DB.
    await seedLocalBinding(db,f);
    const env={...f.env,DB:db};
    (globalThis as unknown as {nongtoriTestEnv:unknown}).nongtoriTestEnv=env;
    const body={farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'};
    const request=(key:string)=>testIdentityProvider.requestAs('worker-a','/api/scouting-field-checks',{
      method:'POST',headers:{'content-type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)});
    const key=crypto.randomUUID();
    const r=await Promise.all([POST(request(key)),POST(request(key))]);
    assert.deepEqual(r.map(x=>x.status),[201,201]);assert.deepEqual(await r[0].json(),await r[1].json());
    const n=async(table:string)=>(await db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).first<{n:number}>())!.n;
    assert.equal(await n('scouting_field_checks'),1);assert.equal(await n('scouting_operation_receipts'),1);
    assert.equal(await n('scouting_operation_guards'),0);
    const before=await db.prepare('SELECT * FROM scouting_location_states').all();
    await db.prepare('CREATE TABLE synthetic_test_failure(accepted INTEGER CONSTRAINT synthetic_batch_failure CHECK(accepted=1))').run();
    // Inject a real CHECK error after the field-check insert in the candidate batch.
    let injectedBatches=0;
    const failing={prepare:db.prepare.bind(db),batch:(statements:D1PreparedStatement[])=>{
      injectedBatches++;
      return db.batch([...statements.slice(0,3),db.prepare('INSERT INTO synthetic_test_failure VALUES(0)'),...statements.slice(3)]);
    }} as D1Database;
    env.DB=failing;
    assert.equal((await POST(request(crypto.randomUUID()))).status,503);
    assert.equal(injectedBatches,1,'a pre-batch failure must not count as rollback proof');
    assert.equal(await n('scouting_field_checks'),1);assert.equal(await n('scouting_operation_receipts'),1);
    assert.deepEqual((await db.prepare('SELECT * FROM scouting_location_states').all()).results,before.results);
    assert.equal(outbound,0);
  }finally{f.sqlite.close();await mf.dispose();}
});
test('four real handlers on local D1 preserve lost-response replay, authorization and full-quota replay',async()=>{
  const h=await localHarness();
  try{
    const key=crypto.randomUUID(),bodies:Partial<Record<Kind,object>>={},results:Partial<Record<Kind,unknown>>={};
    const check={farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'};
    const checked=await h.call('CHECK',check,key);assert.equal(checked.status,201);
    const checkResult=await checked.json() as {fieldCheckId:string};
    bodies.CHECK=check;results.CHECK=checkResult;
    bodies.CORRECTION={farmId:'farm-a',fieldCheckId:checkResult.fieldCheckId,correctionKind:'REPLACE',replacementEvidenceCode:'DIRECT_MITE_OR_EGG_CONFIRMED',reasonCode:'MISCLICK'};
    bodies.ACTION={farmId:'farm-a',locationStateId:'loc',actionCode:'TREATMENT_APPLIED'};
    bodies.RESOLVE={farmId:'farm-a',locationStateId:'loc',reasonCode:'TREATMENT_COMPLETED'};
    for(const kind of ['CORRECTION','ACTION','RESOLVE'] as const){
      const r=await h.call(kind,bodies[kind]!,key);assert.equal(r.status,kind==='RESOLVE'?200:201,await r.clone().text());results[kind]=await r.json();
    }
    // Drop all first responses at the synthetic client boundary; replay after state changes.
    const before=await h.snapshot();
    for(const kind of Object.keys(routes) as Kind[]){
      const replay=await h.call(kind,bodies[kind]!,key);assert.equal(replay.status,kind==='RESOLVE'?200:201);
      assert.deepEqual(await replay.json(),results[kind]);
      assert.equal((await h.call(kind,{...bodies[kind],note:'edited'},key)).status,409);
      assert.equal((await h.call(kind,bodies[kind]!,key,null)).status,403);
      assert.equal((await h.call(kind,bodies[kind]!,key,'owner-b')).status,403);
      assert.equal((await h.call(kind,{...bodies[kind],farmId:'farm-b'},key,'owner-b')).status,400);
    }
    assert.deepEqual(await h.snapshot(),before);
    const n=async(table:string)=>(await h.db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).first<{n:number}>())!.n;
    assert.equal(await n('scouting_field_checks'),1);assert.equal(await n('scouting_field_check_corrections'),1);
    assert.equal(await n('scouting_actions'),1);assert.equal(await n('scouting_case_events'),2);
    assert.equal(await n('scouting_operation_receipts'),4);assert.equal(await n('scouting_operation_guards'),0);
    assert.equal((await h.db.prepare('SELECT primary_evidence_code FROM scouting_field_checks').first<{primary_evidence_code:string}>())!.primary_evidence_code,'NO_VISIBLE_EVIDENCE');
    assert.equal((await h.db.prepare('SELECT state_version FROM scouting_location_states').first<{state_version:number}>())!.state_version,5);
    h.env.SCOUTING_RECEIPT_FARM_LIMIT='4';
    assert.equal((await h.call('ACTION',bodies.ACTION!,crypto.randomUUID())).status,429);
    assert.equal((await h.call('ACTION',bodies.ACTION!,key)).status,201);
    assert.deepEqual(await h.snapshot(),before);
    await h.db.prepare("UPDATE farm_members SET status='INACTIVE' WHERE id='worker-a'").run();
    for(const kind of Object.keys(routes) as Kind[])assert.equal((await h.call(kind,bodies[kind]!,key)).status,403);
    assert.deepEqual(await h.snapshot(),before);
  }finally{await h.close();}
});
test('correction/action/resolve domain and existing audit effects roll back on actual local batch failure',async()=>{
  for(const kind of ['CORRECTION','ACTION','RESOLVE'] as const){
    const h=await localHarness();
    try{
      let body:object;
      if(kind==='CORRECTION'){
        const r=await h.call('CHECK',{farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'},crypto.randomUUID());assert.equal(r.status,201);
        body={farmId:'farm-a',fieldCheckId:(await r.json() as {fieldCheckId:string}).fieldCheckId,correctionKind:'VOID',reasonCode:'MISCLICK'};
      }else body={farmId:'farm-a',locationStateId:'loc',...(kind==='ACTION'?{actionCode:'TREATMENT_APPLIED'}:{reasonCode:'TREATMENT_COMPLETED'})};
      await h.db.prepare('CREATE TABLE synthetic_tail_failure(ok INTEGER CONSTRAINT synthetic_tail_abort CHECK(ok=1))').run();
      const before=await h.snapshot();let batches=0;
      h.env.DB={prepare:h.db.prepare.bind(h.db),batch:(statements:D1PreparedStatement[])=>{
        batches++;return h.db.batch([...statements,h.db.prepare('INSERT INTO synthetic_tail_failure VALUES(0)')]);
      }} as D1Database;
      assert.equal((await h.call(kind,body,crypto.randomUUID())).status,503);
      assert.equal(batches,1);assert.deepEqual(await h.snapshot(),before,`${kind} must roll back receipt, domain, projection and audit`);
    }finally{await h.close();}
  }
});
