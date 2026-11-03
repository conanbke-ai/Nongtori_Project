import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { ScoutingPendingIntent } from '../app/features/pests/presentation/scouting-pending-intent';
const path='/api/scouting-field-checks',body={farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'};
test('ambiguous response preserves immutable key/payload; explicit retry alone resends it',async()=>{
  const requests: RequestInit[]=[];let keys=0;
  const client=new ScoutingPendingIntent(async(_url,init)=>{
    requests.push(init!);if(requests.length===1)throw TypeError('response lost');
    return Response.json({fieldCheckId:'original-check',message:'ok'},{status:201});
  },()=>`key-${++keys}`);
  await assert.rejects(client.request(path,body,'member-a'),/response lost/);
  const pending=client.snapshot();assert.equal(keys,1);assert.equal(requests.length,1);
  await assert.rejects(client.request(path,{...body,farmId:'farm-b'},'member-a'),/UNRESOLVED_INTENT/);
  await assert.rejects(client.request(path,{...body,evidenceCode:'INCONCLUSIVE'},'member-a'),/UNRESOLVED_INTENT/);
  client.discardRejected();assert.deepEqual(client.snapshot(),pending);
  assert.equal(requests.length,1,'no automatic POST on error, edit or scope switch');
  assert.equal((await client.request(path,body,'member-a')).fieldCheckId,'original-check');
  assert.deepEqual(requests[0],requests[1]);assert.equal(keys,1);assert.equal(client.snapshot(),null);
});
test('definite rejection can only be discarded explicitly; malformed success remains uncertain',async()=>{
  let calls=0,keys=0;
  const client=new ScoutingPendingIntent(async()=>{
    calls++;return calls===1?Response.json({code:'INVALID_INTENT',error:'invalid'},{status:422}):Response.json({});
  },()=>`key-${++keys}`);
  await assert.rejects(client.request(path,body,'member-a'),/invalid/);assert.equal(client.snapshot()?.rejected,true);
  await assert.rejects(client.request(path,{...body,locationStateId:'other'},'member-a'),/UNRESOLVED_INTENT/);assert.equal(keys,1);
  client.discardRejected();assert.equal(client.snapshot(),null);
  await assert.rejects(client.request(path,body,'member-a'),/INVALID_RESPONSE/);assert.equal(client.snapshot()?.rejected,false);
  client.discardRejected();assert.notEqual(client.snapshot(),null);
});
test('pending request cannot double-submit; storage/reload and runtime opt-in are absent by default',async()=>{
  let complete!: (r: Response)=>void,calls=0;
  const client=new ScoutingPendingIntent(async()=>{calls++;return new Promise(resolve=>{complete=resolve;});});
  const first=client.request(path,body,'member-a');
  await assert.rejects(client.request(path,body,'member-a'),/PENDING_INTENT/);assert.equal(calls,1);
  complete(Response.json({fieldCheckId:'one'}));await first;
  const source=readFileSync('app/features/pests/presentation/scouting-pending-intent.ts','utf8');
  assert.equal(/localStorage|sessionStorage|indexedDB|setTimeout|setInterval/.test(source),false);
  assert.match(readFileSync('app/features/pests/presentation/ScoutingQueue.tsx','utf8'),/keyedMutations = false/);
});
test('uncertain planning/server failure never enables discard or rotates the key',async()=>{
  let keys=0;
  const client=new ScoutingPendingIntent(async()=>Response.json({code:'MUTATION_RESULT_UNCERTAIN',error:'uncertain'},{status:503}),()=>`key-${++keys}`);
  await assert.rejects(client.request(path,body,'member-a'),/uncertain/);
  assert.equal(client.snapshot()?.rejected,false);client.discardRejected();assert.notEqual(client.snapshot(),null);
  await assert.rejects(client.request(path,{...body,locationStateId:'different'},'member-a'),/UNRESOLVED_INTENT/);
  assert.equal(keys,1);
});
test('missing or changed actor scope cannot resend an unresolved intent under another member',async()=>{
  let calls=0;
  const client=new ScoutingPendingIntent(async()=>{calls++;throw TypeError('lost');});
  await assert.rejects(client.request(path,body,''),/UNVERIFIED_ACTOR/);assert.equal(calls,0);
  await assert.rejects(client.request(path,body,'member-a'),/lost/);
  await assert.rejects(client.request(path,body,'member-b'),/UNRESOLVED_ACTOR/);
  assert.equal(calls,1);assert.equal(client.snapshot()?.memberId,'member-a');
});
test('a retry after definite rejection becomes uncertain again if its response is lost',async()=>{
  let calls=0,keys=0;
  const client=new ScoutingPendingIntent(async()=>{
    calls++;if(calls===1)return Response.json({code:'RECEIPT_LIMIT',error:'limit'},{status:429});
    throw TypeError('lost after retry');
  },()=>`key-${++keys}`);
  await assert.rejects(client.request(path,body,'member-a'),/limit/);assert.equal(client.snapshot()?.rejected,true);
  await assert.rejects(client.request(path,body,'member-a'),/lost after retry/);
  assert.equal(client.snapshot()?.rejected,false);client.discardRejected();
  assert.notEqual(client.snapshot(),null);assert.equal(keys,1);
});
test('once uncertain, later explicit rejections cannot release an earlier in-flight intent',async()=>{
  for(const [status,code] of [[400,'INVALID_MUTATION'],[403,'FORBIDDEN'],[429,'RECEIPT_LIMIT']] as const) {
    let calls=0,keys=0;
    const client=new ScoutingPendingIntent(async()=>{
      calls++;if(calls===1)throw TypeError('lost');return Response.json({code,error:'rejected'},{status});
    },()=>`key-${++keys}`);
    await assert.rejects(client.request(path,body,'member-a'),/lost/);
    await assert.rejects(client.request(path,body,'member-a'),/rejected/);
    assert.equal(client.snapshot()?.uncertain,true);assert.equal(client.snapshot()?.rejected,false);
    client.discardRejected();assert.notEqual(client.snapshot(),null);assert.equal(keys,1);
  }
});
