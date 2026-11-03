// New synthetic memory bindings only. No deployment, real D1 or feature activation.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider } from './support/test-identity-provider';
import { ScoutingPendingIntent } from '../app/features/pests/presentation/scouting-pending-intent';
const routes={
  CHECK:(await import('../app/api/scouting-field-checks/route')).POST,
  CORRECTION:(await import('../app/api/scouting-field-check-corrections/route')).POST,
  ACTION:(await import('../app/api/scouting-actions/route')).POST,
  RESOLVE:(await import('../app/api/scouting-resolve/route')).POST,
};
type Kind=keyof typeof routes;
const paths={CHECK:'/api/scouting-field-checks',CORRECTION:'/api/scouting-field-check-corrections',ACTION:'/api/scouting-actions',RESOLVE:'/api/scouting-resolve'};
type Fixture=ReturnType<typeof scoutingIntentFixture>;
function activate(f:Fixture){(globalThis as unknown as {nongtoriTestEnv:unknown}).nongtoriTestEnv=f.env;}
function call(kind:Kind,body:object,key=crypto.randomUUID()){
  return routes[kind](testIdentityProvider.requestAs('worker-a',paths[kind],{method:'POST',headers:{'content-type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)}));
}
const count=(f:Fixture,table:string)=>(f.sqlite.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get() as {n:number}).n;
async function bodyFor(kind:Kind){
  if(kind==='CHECK')return {farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'};
  if(kind==='CORRECTION'){
    const r=await call('CHECK',{farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'});
    assert.equal(r.status,201);
    return {farmId:'farm-a',fieldCheckId:(await r.json() as {fieldCheckId:string}).fieldCheckId,correctionKind:'VOID',reasonCode:'MISCLICK'};
  }
  if(kind==='ACTION')return {farmId:'farm-a',locationStateId:'loc',actionCode:'TREATMENT_APPLIED'};
  return {farmId:'farm-a',locationStateId:'loc',reasonCode:'TREATMENT_COMPLETED'};
}
test('all four real handlers and memory client recover lost responses after revoked membership without rotating keys',async()=>{
  for(const kind of Object.keys(routes) as Kind[]){
    const f=scoutingIntentFixture();activate(f);
    try{
      const body=await bodyFor(kind),requestKeys:string[]=[],statuses:number[]=[],codes:(string|null)[]=[];let keys=0,firstResult:unknown;
      const domainTable={CHECK:'scouting_field_checks',CORRECTION:'scouting_field_check_corrections',ACTION:'scouting_actions',RESOLVE:'scouting_case_events'}[kind];
      const domainBefore=count(f,domainTable),receiptsBefore=count(f,'scouting_operation_receipts');
      const client=new ScoutingPendingIntent(async(_url,init)=>{
        const req=testIdentityProvider.requestAs('worker-a',paths[kind],init);
        requestKeys.push(req.headers.get('Idempotency-Key')!);
        const response=await routes[kind](req);
        statuses.push(response.status);
        codes.push((await response.clone().json() as {code?:string}).code??null);
        if(requestKeys.length===1){
          assert.equal(response.status,kind==='RESOLVE'?200:201);
          firstResult=await response.clone().json();throw TypeError('SYNTHETIC_RESPONSE_LOSS_AFTER_COMMIT');
        }
        return response;
      },()=>{keys++;return crypto.randomUUID();});
      await assert.rejects(client.request(paths[kind],body,'worker-a'),/SYNTHETIC_RESPONSE_LOSS/);
      assert.equal(count(f,domainTable),domainBefore+1);assert.equal(count(f,'scouting_operation_receipts'),receiptsBefore+1);
      const committed=f.snapshot();
      f.sqlite.exec("UPDATE farm_members SET status='INACTIVE' WHERE id='worker-a'");
      await assert.rejects(client.request(paths[kind],body,'worker-a'));
      assert.equal(client.snapshot()?.uncertain,true);assert.equal(client.snapshot()?.rejected,false);
      client.discardRejected();assert.notEqual(client.snapshot(),null);
      await assert.rejects(client.request(paths[kind],body,'owner-a'),/UNRESOLVED_ACTOR/);
      await assert.rejects(client.request(paths[kind],{...body,note:'edited while uncertain'},'worker-a'),/UNRESOLVED_INTENT/);
      assert.equal(requestKeys.length,2,'no hidden POST for scope/edit/discard');
      assert.deepEqual(f.snapshot(),committed);
      f.sqlite.exec("UPDATE farm_members SET status='ACTIVE' WHERE id='worker-a'");
      assert.deepEqual(await client.request(paths[kind],body,'worker-a'),firstResult);
      assert.equal(keys,1);assert.equal(new Set(requestKeys).size,1);assert.equal(client.snapshot(),null);
      assert.deepEqual(statuses,[kind==='RESOLVE'?200:201,403,kind==='RESOLVE'?200:201]);
      assert.deepEqual(codes,[null,'FORBIDDEN',null],'check codes outside the rejected transport promise');
      assert.deepEqual(f.snapshot(),committed);
    }finally{f.sqlite.close();}
  }
});
test('same-key concurrent different payloads produce exactly one committed action and one conflict',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const key=crypto.randomUUID(),body={farmId:'farm-a',locationStateId:'loc',actionCode:'OBSERVE_ONLY'};
    const requests=[body,{...body,note:'a distinct intent'}];
    const results=await Promise.all(requests.map(body=>call('ACTION',body,key)));
    assert.deepEqual(results.map(r=>r.status).sort(),[201,409]);
    const winner=results.findIndex(r=>r.status===201),row=f.sqlite.prepare('SELECT note FROM scouting_actions').get() as {note:string|null};
    assert.equal((await results[1-winner].clone().json() as {code:string}).code,'INTENT_CONFLICT');
    assert.equal(row.note,winner===0?null:'a distinct intent');
    assert.equal(count(f,'scouting_actions'),1);assert.equal(count(f,'scouting_operation_receipts'),1);
    assert.equal(count(f,'scouting_case_events'),0,'do not invent an action case-event contract');
    const before=f.snapshot();
    assert.equal((await call('ACTION',requests[winner],key)).status,201);
    assert.equal((await call('ACTION',requests[1-winner],key)).status,409);
    assert.deepEqual(f.snapshot(),before);
  }finally{f.sqlite.close();}
});
test('canonical nested ordering and omitted timestamp preserve original check result and stored evidence',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const key=crypto.randomUUID(),body={farmId:'farm-a',locationStateId:'loc',evidenceCode:'INCONCLUSIVE',secondaryEvidence:{a:1,b:2}};
    const first=await call('CHECK',body,key);assert.equal(first.status,201);const result=await first.json(),before=f.snapshot();
    const replay=await call('CHECK',{...body,checkedAt:null,secondaryEvidence:{b:2,a:1}},key);
    assert.equal(replay.status,201);assert.deepEqual(await replay.json(),result);assert.deepEqual(f.snapshot(),before);
    assert.equal((await call('CHECK',{...body,checkedAt:'2026-01-01T00:00:00Z'},key)).status,409);
    assert.deepEqual(f.snapshot(),before);
  }finally{f.sqlite.close();}
});
test('aged receipt remains replayable and consumes synthetic quota without adopting an expiry policy',async()=>{
  const f=scoutingIntentFixture();activate(f);f.env.SCOUTING_RECEIPT_FARM_LIMIT='1';
  try{
    const key=crypto.randomUUID(),body={farmId:'farm-a',locationStateId:'loc',actionCode:'OBSERVE_ONLY'};
    const first=await call('ACTION',body,key);assert.equal(first.status,201);const result=await first.json();
    f.sqlite.exec("UPDATE scouting_operation_receipts SET committed_at='2000-01-01T00:00:00Z'");
    const before=f.snapshot(),replay=await call('ACTION',body,key);
    assert.equal(replay.status,201);assert.deepEqual(await replay.json(),result);
    const exhausted=await call('ACTION',body);assert.equal(exhausted.status,429);
    assert.equal((await exhausted.json() as {code:string}).code,'RECEIPT_LIMIT');
    assert.deepEqual(f.snapshot(),before);assert.equal(count(f,'scouting_operation_receipts'),1);
  }finally{f.sqlite.close();}
});
test('truthy opt-in and malformed synthetic limits never activate keyed mutation writes',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const body={farmId:'farm-a',locationStateId:'loc',actionCode:'OBSERVE_ONLY'},before=f.snapshot();
    const env=f.env as unknown as Record<string,unknown>;
    for(const value of [true,1,'TRUE','1','yes']){
      env.SCOUTING_MUTATION_IDEMPOTENCY=value;
      const r=await call('ACTION',body);assert.equal(r.status,503);
      assert.equal((await r.json() as {code:string}).code,'IDEMPOTENCY_DISABLED');assert.deepEqual(f.snapshot(),before);
    }
    env.SCOUTING_MUTATION_IDEMPOTENCY='true';
    for(const name of ['SCOUTING_RECEIPT_FARM_LIMIT','SCOUTING_RECEIPT_MEMBER_LIMIT']){
      for(const value of ['0','-1','1.5','1e2','9007199254740992','Infinity',10]){
        env[name]=value;const r=await call('ACTION',body);assert.equal(r.status,503);
        assert.equal((await r.json() as {code:string}).code,'IDEMPOTENCY_DISABLED');assert.deepEqual(f.snapshot(),before);
      }
      env[name]='100';
    }
  }finally{f.sqlite.close();}
});
