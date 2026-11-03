import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { isValidElement, type ReactNode } from 'react';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider } from './support/test-identity-provider';
import { ScoutingPendingIntent } from '../app/features/pests/presentation/scouting-pending-intent';
const lookup=(await import('../app/api/scouting-mutation-status/route')).POST;
const routes={
  CHECK:(await import('../app/api/scouting-field-checks/route')).POST,
  CORRECTION:(await import('../app/api/scouting-field-check-corrections/route')).POST,
  ACTION:(await import('../app/api/scouting-actions/route')).POST,
  RESOLVE:(await import('../app/api/scouting-resolve/route')).POST,
};
type Kind=keyof typeof routes;
type Fixture=ReturnType<typeof scoutingIntentFixture>;
const paths={CHECK:'/api/scouting-field-checks',CORRECTION:'/api/scouting-field-check-corrections',ACTION:'/api/scouting-actions',RESOLVE:'/api/scouting-resolve'};
function activate(f:Fixture){(globalThis as unknown as {nongtoriTestEnv:unknown}).nongtoriTestEnv=f.env;}
function request(kind:Kind,body:object,key:string,actor:'worker-a'|'owner-a'|'owner-b'|null='worker-a'){
  return testIdentityProvider.requestAs(actor,'/api/scouting-mutation-status',{method:'POST',headers:{
    'content-type':'application/json','Idempotency-Key':key,'Scouting-Operation':kind},body:JSON.stringify(body)});
}
async function bodyFor(kind:Kind){
  if(kind==='CHECK')return {farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'};
  if(kind==='CORRECTION'){
    const r=await routes.CHECK(request('CHECK',{farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'},crypto.randomUUID()));
    assert.equal(r.status,201);return {farmId:'farm-a',fieldCheckId:(await r.json() as {fieldCheckId:string}).fieldCheckId,
      correctionKind:'VOID',reasonCode:'MISCLICK'};
  }
  return {farmId:'farm-a',locationStateId:'loc',...(kind==='ACTION'?{actionCode:'TREATMENT_APPLIED'}:{reasonCode:'TREATMENT_COMPLETED'})};
}
function noWrites(sql:string[]){
  assert.equal(sql.some(s=>/\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|BATCH_BEGIN)\b/i.test(s)),false,JSON.stringify(sql));
}
test('all four result lookups return original committed DTO with zero domain/receipt/quota writes',async()=>{
  for(const kind of Object.keys(routes) as Kind[]){
    const f=scoutingIntentFixture();activate(f);
    try{
      const body=await bodyFor(kind),key=crypto.randomUUID();
      const saved=await routes[kind](request(kind,body,key));assert.equal(saved.status,kind==='RESOLVE'?200:201);
      const result=await saved.json(),before=f.snapshot(),start=f.observedSql.length;
      f.env.SCOUTING_RECEIPT_FARM_LIMIT=''; // lookup is not a new-intent quota claim
      const checked=await lookup(request(kind,body,key));
      assert.equal(checked.status,200);assert.equal(checked.headers.get('cache-control'),'no-store');
      assert.deepEqual(await checked.json(),{state:'COMMITTED',originalStatus:saved.status,result});
      assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
    }finally{f.sqlite.close();}
  }
});
test('receipt miss stays UNCONFIRMED and never reserves a receipt or declares failed/not-saved',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const body=await bodyFor('ACTION'),before=f.snapshot(),start=f.observedSql.length;
    for(let i=0;i<2;i++){
      const r=await lookup(request('ACTION',body,crypto.randomUUID()));assert.equal(r.status,200);
      assert.deepEqual(await r.json(),{state:'UNCONFIRMED'});
    }
    assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
  }finally{f.sqlite.close();}
});
test('current membership, farm/target ownership and hash conflict protect read confirmation',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const body=await bodyFor('ACTION'),key=crypto.randomUUID();assert.equal((await routes.ACTION(request('ACTION',body,key))).status,201);
    const before=f.snapshot(),start=f.observedSql.length;
    for(const actor of [null,'owner-b'] as const)assert.equal((await lookup(request('ACTION',body,key,actor))).status,403);
    const otherMember=await lookup(request('ACTION',body,key,'owner-a'));
    assert.deepEqual(await otherMember.json(),{state:'UNCONFIRMED'},'same-farm different actor cannot get original receipt');
    assert.equal((await lookup(request('ACTION',{...body,farmId:'farm-b'},key,'owner-b'))).status,400);
    assert.equal((await lookup(request('ACTION',{...body,note:'different'},key))).status,409);
    f.sqlite.exec("UPDATE farm_members SET status='INACTIVE' WHERE id='worker-a'");
    assert.equal((await lookup(request('ACTION',body,key))).status,403);
    assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
  }finally{f.sqlite.close();}
});
test('lookup defaults off and fails unavailable rather than bootstrapping or writing',async()=>{
  for(const mode of ['off','schema','read']){
    const f=scoutingIntentFixture(mode!=='schema');activate(f);
    try{
      const body=await bodyFor('ACTION'),before=f.snapshot(),start=f.observedSql.length;
      if(mode==='off')f.env.SCOUTING_MUTATION_IDEMPOTENCY='';
      if(mode==='read')f.failReadContaining('FROM scouting_operation_receipts');
      const r=await lookup(request('ACTION',body,crypto.randomUUID()));assert.equal(r.status,503);
      assert.equal(r.headers.get('cache-control'),'no-store');assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
    }finally{f.sqlite.close();}
  }
});
test('manual confirmation recovers a lost response without resending the original mutation POST',async()=>{
  for(const kind of Object.keys(routes) as Kind[]){
    const f=scoutingIntentFixture();activate(f);
    try{
      const body=await bodyFor(kind),calls:{url:string;key:string|null;body:BodyInit|null|undefined}[]=[];let generated=0,original:unknown;
      const client=new ScoutingPendingIntent(async(url,init)=>{
        calls.push({url:String(url),key:new Headers(init?.headers).get('Idempotency-Key'),body:init?.body});
        const req=testIdentityProvider.requestAs('worker-a',String(url),init);
        if(String(url)==='/api/scouting-mutation-status')return lookup(req);
        const r=await routes[kind](req);assert.equal(r.status,kind==='RESOLVE'?200:201);
        original=await r.json();throw TypeError('SYNTHETIC_RESPONSE_LOSS');
      },()=>{generated++;return crypto.randomUUID();});
      await assert.rejects(client.request(paths[kind],body,'worker-a'),/SYNTHETIC_RESPONSE_LOSS/);
      const before=f.snapshot(),start=f.observedSql.length;
      assert.deepEqual(await client.confirm('worker-a','farm-a'),{state:'COMMITTED',result:original});
      assert.equal(client.snapshot(),null);assert.equal(generated,1);
      assert.deepEqual(calls.map(c=>c.url),[paths[kind],'/api/scouting-mutation-status']);
      assert.equal(calls[0].key,calls[1].key);assert.equal(calls[0].body,calls[1].body);
      assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
    }finally{f.sqlite.close();}
  }
});
test('miss/error/conflict preserve uncertain intent; actor/farm changes cannot issue a lookup',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const body=await bodyFor('ACTION'),urls:string[]=[];let generated=0;
    const client=new ScoutingPendingIntent(async(url,init)=>{
      urls.push(String(url));
      if(String(url)!=='/api/scouting-mutation-status')throw TypeError('SYNTHETIC_LOSS_BEFORE_DISPATCH');
      return lookup(testIdentityProvider.requestAs('worker-a',String(url),init));
    },()=>{generated++;return crypto.randomUUID();});
    await assert.rejects(client.request(paths.ACTION,body,'worker-a'),/SYNTHETIC_LOSS/);
    const intent=client.snapshot()!,before=f.snapshot();
    await assert.rejects(client.confirm('owner-a','farm-a'),/UNRESOLVED_ACTOR/);
    await assert.rejects(client.confirm('worker-a','farm-b'),/UNRESOLVED_FARM/);assert.equal(urls.length,1);
    assert.deepEqual(await client.confirm('worker-a','farm-a'),{state:'UNCONFIRMED'});
    client.discardRejected();assert.deepEqual(client.snapshot(),intent);assert.equal(generated,1);
    f.failReadContaining('FROM scouting_operation_receipts');await assert.rejects(client.confirm('worker-a','farm-a'));
    assert.deepEqual(client.snapshot(),intent);assert.deepEqual(f.snapshot(),before);
    // Different payload under the same retained key is committed by an independent synthetic request.
    const other=await routes.ACTION(request('ACTION',{...body,note:'conflicting'},intent.key));assert.equal(other.status,201);
    const after=f.snapshot();await assert.rejects(client.confirm('worker-a','farm-a'));
    assert.deepEqual(client.snapshot(),intent);assert.deepEqual(f.snapshot(),after);
    assert.equal(urls.filter(url=>url===paths.ACTION).length,1,'no automatic mutation retry');
  }finally{f.sqlite.close();}
});
test('malformed confirmation cannot release a pending key and UI confirmation stays manual/default-off',async()=>{
  let calls=0;
  const client=new ScoutingPendingIntent(async()=>{
    if(++calls===1)throw TypeError('lost');
    return Response.json({state:'COMMITTED',originalStatus:201,result:{}});
  });
  const body={farmId:'farm-a',locationStateId:'loc',actionCode:'OBSERVE_ONLY'};
  await assert.rejects(client.request(paths.ACTION,body,'worker-a'),/lost/);
  const before=client.snapshot();await assert.rejects(client.confirm('worker-a','farm-a'),/INVALID_RESPONSE/);
  assert.deepEqual(client.snapshot(),before);
  const source=readFileSync('app/features/pests/presentation/ScoutingQueue.tsx','utf8');
  assert.match(source,/keyedMutations = false/);assert.match(source,/onClick=\{\(\) => void confirmPending\(\)\}/);
  assert.ok(source.includes('저장 결과만 조회'));assert.ok(source.includes('실패로 단정하지 않고'));
});

// Deterministic component-callback harness, not a DOM/browser renderer. Only this
// component's hooks are replaced; its actual event handlers and client run.
test('late confirmation or explicit retry cannot update a changed/unmounted context or supersede its list request',async()=>{
  type State={value:unknown};type Ref={current:unknown};
  type Effect={deps:unknown[];cleanup?:()=>void};
  let active:{state:(v:unknown)=>unknown;ref:(v:unknown)=>unknown;effect:(f:()=>void|(()=>void),d:unknown[],layout?:boolean)=>void;callback:(f:unknown,d:unknown[])=>unknown};
  const hookKey='nongtoriConfirmationReviewHooks';
  Object.defineProperty(globalThis,hookKey,{configurable:true,get:()=>active});
  const hook=registerHooks({
    resolve(specifier,context,next){
      if(specifier==='react'&&context.parentURL?.endsWith('/ScoutingQueue.tsx'))return {url:'test:confirmation-hooks',shortCircuit:true};
      return next(specifier,context);
    },
    load(url,context,next){
      if(url==='test:confirmation-hooks')return {format:'module',shortCircuit:true,source:
        `export const useState=v=>globalThis.${hookKey}.state(v);export const useRef=v=>globalThis.${hookKey}.ref(v);export const useEffect=(f,d)=>globalThis.${hookKey}.effect(f,d);export const useLayoutEffect=(f,d)=>globalThis.${hookKey}.effect(f,d,true);export const useMemo=f=>f();export const useCallback=(f,d)=>globalThis.${hookKey}.callback(f,d);`};
      return next(url,context);
    },
  });
  const originalFetch=globalThis.fetch;
  try{
    const {ScoutingQueue}=await import('../app/features/pests/presentation/ScoutingQueue');
    const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
    for(const timing of ['after-effects','before-passive-effects'] as const){
    for(const action of ['confirm','retry'] as const){
    for(const change of ['farm','member','permission','roundtrip','unmount'] as const){
      for(const outcome of ['committed','missing','error'] as const){
        const calls:string[]=[],states:State[]=[],refs:Ref[]=[],effects:Effect[]=[];let changed=0;
        let stateIndex=0,refIndex=0,effectIndex=0,callbackIndex=0;const tasks:{run:()=>void;layout:boolean}[]=[];
        const callbacks:{fn:unknown;deps:unknown[]}[]=[];
        active={
          state(initial){const box=states[stateIndex++]??(states[stateIndex-1]={value:initial});
            return [box.value,(v:unknown)=>{box.value=typeof v==='function'?(v as (old:unknown)=>unknown)(box.value):v;}];},
          ref(initial){return refs[refIndex++]??(refs[refIndex-1]={current:initial});},
          effect(run,deps,layout=false){const index=effectIndex++,previous=effects[index];
            if(!previous||deps.some((v,i)=>!Object.is(v,previous.deps[i])))tasks.push({layout,run:()=>{
              previous?.cleanup?.();effects[index]={deps,cleanup:run()||undefined};
            }});},
          callback(fn,deps){const index=callbackIndex++,previous=callbacks[index];
            if(!previous||deps.some((v,i)=>!Object.is(v,previous.deps[i])))callbacks[index]={fn,deps};
            return callbacks[index].fn;},
        };
        globalThis.fetch=async(url)=>{calls.push(String(url));return Response.json({rows:[]});};
        let props:Parameters<typeof ScoutingQueue>[0]={farmId:'farm-a',mutationMemberId:'worker-a',canReview:true,language:'ko',keyedMutations:true,onChanged:()=>{changed++;}};
        const render=(flushPassive=true)=>{
          stateIndex=refIndex=effectIndex=callbackIndex=0;const tree=ScoutingQueue(props);
          for(const task of tasks.splice(0)){if(task.layout||flushPassive)task.run();else tasks.push(task);}
          return tree;
        };
        render();await flush();
        let complete!:(r:Response)=>void,initial=true;
        const client=new ScoutingPendingIntent(async(url)=>{
          calls.push(String(url));
          if(initial){initial=false;throw TypeError('synthetic response loss');}
          return new Promise<Response>(resolve=>{complete=resolve;});
        });
        await assert.rejects(client.request(paths.CHECK,{farmId:'farm-a',locationStateId:'loc',evidenceCode:'NO_VISIBLE_EVIDENCE'},'worker-a'),/synthetic response loss/);
        // The pending-client ref and final pending-state hook are the real
        // component's existing memory-only entry point, not a runtime auth bypass.
        const clientRef=refs.find(r=>r.current===null);assert.ok(clientRef);clientRef.current=client;
        const pendingState=states.at(-1);assert.ok(pendingState);pendingState.value=client.snapshot();
        const findButton=(node:ReactNode):(()=>void)|undefined=>{
          if(Array.isArray(node)){for(const child of node){const found=findButton(child);if(found)return found;}return;}
          if(!isValidElement<{children?:ReactNode;onClick?:()=>void}>(node))return;
          if(node.type==='button'&&node.props.children===(action==='confirm'?'저장 결과만 조회':'같은 키로 저장 재시도'))return node.props.onClick;
          return findButton(node.props.children);
        };
        const click=findButton(render());assert.ok(click);click();await flush();
        assert.equal(calls.filter(url=>url==='/api/scouting-mutation-status').length,action==='confirm'?1:0);
        assert.equal(calls.filter(url=>url===paths.CHECK).length,action==='confirm'?1:2);
        if(change==='farm'||change==='roundtrip')props={...props,farmId:'farm-b'};
        if(change==='member')props={...props,mutationMemberId:'owner-a'};
        if(change==='permission')props={...props,canReview:false};
        if(change==='unmount'){for(const effect of effects)effect.cleanup?.();}else render(timing==='after-effects');await flush();
        if(change==='roundtrip'){props={...props,farmId:'farm-a'};render(timing==='after-effects');await flush();}
        const callCount=calls.length;
        const result={fieldCheckId:'old-private-check',message:'old-private-message'};
        complete(outcome==='error'?Response.json({error:'old-private-error'},{status:503}):Response.json(outcome==='missing'?{state:'UNCONFIRMED'}:
          action==='confirm'?{state:'COMMITTED',originalStatus:201,result}:result));
        await flush();const tree=change==='unmount'?null:render(false);await flush();
        assert.equal(calls.length,callCount,`${timing}/${change}/${outcome}: old response must not issue an old-scope list refresh`);
        assert.equal(changed,0,`${timing}/${change}/${outcome}: old response must not fire onChanged`);
        const text=JSON.stringify(tree);
        assert.equal(/old-private-(error|check|message)/.test(text),false,`${change}/${outcome}: no stale feedback or check panel`);
      }
    }
    }
    }
  }finally{globalThis.fetch=originalFetch;hook.deregister();Reflect.deleteProperty(globalThis,hookKey);}
});

test('in-flight confirmation blocks duplicate lookup/mutation and failure releases only the busy lock',async()=>{
  let calls=0,keys=0,complete!:(response:Response)=>void;
  const client=new ScoutingPendingIntent(async()=>{
    if(++calls===1)throw TypeError('lost');
    return new Promise<Response>(resolve=>{complete=resolve;});
  },()=>{keys++;return crypto.randomUUID();});
  const body={farmId:'farm-a',locationStateId:'loc',actionCode:'OBSERVE_ONLY'};
  await assert.rejects(client.request(paths.ACTION,body,'worker-a'),/lost/);
  const original=client.snapshot(),first=client.confirm('worker-a','farm-a');
  await assert.rejects(client.confirm('worker-a','farm-a'),/PENDING_INTENT/);
  await assert.rejects(client.request(paths.ACTION,body,'worker-a'),/PENDING_INTENT/);
  client.discardRejected();assert.deepEqual(client.snapshot(),original);assert.equal(calls,2);
  complete(Response.json({error:'unavailable'},{status:503}));await assert.rejects(first,/unavailable/);
  assert.deepEqual(client.snapshot(),original);assert.equal(keys,1);assert.equal(calls,2);
  const second=client.confirm('worker-a','farm-a');
  complete(Response.json({state:'UNCONFIRMED'}));assert.deepEqual(await second,{state:'UNCONFIRMED'});
  assert.deepEqual(client.snapshot(),original);assert.equal(keys,1);assert.equal(calls,3);
});

test('invalid keys, operation and malformed/oversized bodies never disclose a stored receipt or write',async()=>{
  const f=scoutingIntentFixture();activate(f);
  try{
    const body=await bodyFor('ACTION'),key=crypto.randomUUID();
    assert.equal((await routes.ACTION(request('ACTION',body,key))).status,201);
    const before=f.snapshot(),start=f.observedSql.length;
    const variants=[
      {key:'invalid',operation:'ACTION',body:JSON.stringify(body)},
      {key,operation:'INVALID',body:JSON.stringify(body)},
      {key,operation:'ACTION',body:'{"secret-note":'},
      {key,operation:'ACTION',body:JSON.stringify({...body,note:'secret-note'.repeat(2000)})},
    ];
    for(const variant of variants){
      const req=testIdentityProvider.requestAs('worker-a','/api/scouting-mutation-status',{method:'POST',headers:{
        'Idempotency-Key':variant.key,'Scouting-Operation':variant.operation},body:variant.body});
      const result=await lookup(req);assert.equal(result.status,422);
      assert.equal(result.headers.get('cache-control'),'no-store');
      const text=await result.text();assert.equal(text.includes('secret-note'),false);
      assert.equal(text.includes('response_json'),false);assert.equal(text.includes(key),false);
      assert.equal(text.includes('COMMITTED'),false);
    }
    assert.deepEqual(f.snapshot(),before);noWrites(f.observedSql.slice(start));
  }finally{f.sqlite.close();}
});
