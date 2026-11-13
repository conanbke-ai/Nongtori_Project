import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHooks } from 'node:module';
import type { FormEvent, ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { submitPestCapture, pestCaptureGuidance } from '../app/features/pests/presentation/pest-capture-submission';
import { pestTargets, type PestLanguage } from '../app/features/pests/domain/catalog';
import { captureFileIssue, MAX_CAPTURE_TOTAL_BYTES } from '../app/features/pests/domain/capture-file-rules';
import { pestText } from '../app/features/pests/presentation/text';

test('사진 사전 점검은 기존 합계 경계·선택 열화상·빈 MIME 위임을 유지한다',()=>{
  const image=(size:number,type='image/png')=>({size,type});
  assert.equal(MAX_CAPTURE_TOTAL_BYTES,40*1024*1024);
  assert.equal(captureFileIssue(null,null),'fileRequired');
  assert.equal(captureFileIssue(image(0),image(1)),'fileRequired');
  assert.equal(captureFileIssue(image(MAX_CAPTURE_TOTAL_BYTES),null),null);
  assert.equal(captureFileIssue(image(MAX_CAPTURE_TOTAL_BYTES-1),image(1)),null);
  assert.equal(captureFileIssue(image(MAX_CAPTURE_TOTAL_BYTES),image(1)),'fileSize');
  assert.equal(captureFileIssue(image(1,'application/pdf'),null),'fileImage');
  assert.equal(captureFileIssue(image(1),image(1,'video/mp4')),'fileImage');
  assert.equal(captureFileIssue(image(1),image(0,'application/octet-stream')),null);
  assert.equal(captureFileIssue(image(1,''),image(1,'')),null,'빈 MIME은 서버에서 최종 판단');
});

test('사진 사전 점검 안내는 기존 지원 언어 모두에서 합계·재선택 행동을 제공한다',()=>{
  const serverChecks={ko:'파일 정보와 업로드 조건',vi:'thông tin tệp và điều kiện tải lên',th:'ข้อมูลไฟล์และเงื่อนไขการอัปโหลด','zh-CN':'文件信息和上传条件'};
  for(const language of ['ko','vi','th','zh-CN'] as PestLanguage[]){
    assert.match(pestText(language,'fileHelp'),/40MB/);
    assert.ok(pestText(language,'fileHelp').includes(serverChecks[language]),'서버가 실제 검사하는 정보/조건만 안내');
    assert.doesNotMatch(pestText(language,'fileHelp'),/내용|nội dung|เนื้อหา|内容/,'실제 파일 내용 검사를 약속하지 않음');
    for(const key of ['fileRequired','fileImage','fileSize'] as const)assert.ok(pestText(language,key).length>0);
  }
});

function bodyFor(pestCode='MITE') { const body=new FormData();body.set('farmId','SYNTHETIC_FARM');body.set('itemId','SYNTHETIC_ITEM');body.set('pestCode',pestCode);return body; }
const receipt=(pestCode='MITE')=>({sessionId:'a7ea25a0-9a42-4e92-980f-9467ccf9967e',pestCode,processingStatus:'UPLOADED_AWAITING_MODEL'});

test('every catalog target receives only a filing receipt, never a model diagnosis or confidence',async()=>{
  for(const target of pestTargets){
    let calls=0,refreshes=0;
    const body=bodyFor(target.code),before=[...body.entries()];
    const result=await submitPestCapture(body,{send:async(url,init)=>{
      calls++;assert.equal(url,'/api/pest-capture');assert.equal(init?.method,'POST');assert.equal(init?.body,body);
      return Response.json(receipt(target.code),{status:201});
    },onReceived:()=>{refreshes++;}});
    assert.deepEqual(result,{kind:'received',sessionId:receipt().sessionId,pestCode:target.code,refreshFailed:false});
    assert.deepEqual([...body.entries()],before);assert.equal(calls,1);assert.equal(refreshes,1);
    assert.equal('confidence' in result,false);assert.equal('diagnosis' in result,false);
  }
});

test('only matching201 receipt is received; malformed, pending and foreign target responses stay uncertain',async()=>{
  for(const [status,value] of [[201,{}],[201,null],[201,[]],[201,{...receipt(),sessionId:'not-a-session'}],
    [201,receipt('APHID')],[201,{...receipt(),processingStatus:'COMPLETED'}],[202,receipt()],[200,receipt()],[400,{error:'PRIVATE_DATABASE_STACK'}],[503,{error:'PRIVATE_DATABASE_STACK'}]] as const){
    let calls=0,refreshes=0;
    const result=await submitPestCapture(bodyFor(),{send:async()=>{calls++;return Response.json(value,{status});},onReceived:()=>{refreshes++;}});
    assert.deepEqual(result,{kind:'uncertain'});assert.equal(calls,1);assert.equal(refreshes,0);
    assert.equal(JSON.stringify(result).includes('PRIVATE_DATABASE_STACK'),false);
  }
  for(const send of [async()=>{throw Error('PRIVATE_NETWORK_STACK');},async()=>new Response('not-json',{status:201})]){
    assert.deepEqual(await submitPestCapture(bodyFor(),{send}),{kind:'uncertain'});
  }
});

test('known precommit rejection preserves input and never invokes received refresh',async()=>{
  for(const status of [403,413,422]){
    const body=bodyFor(),before=[...body.entries()];let refreshes=0;
    assert.deepEqual(await submitPestCapture(body,{send:async()=>Response.json({error:'PRIVATE_ERROR'},{status}),onReceived:()=>{refreshes++;}}),{kind:'rejected'});
    assert.deepEqual([...body.entries()],before);assert.equal(refreshes,0);
  }
  let calls=0;
  assert.deepEqual(await submitPestCapture(bodyFor('NOT_A_CATALOG_ENTRY'),{send:async()=>{calls++;return Response.json(receipt());}}),{kind:'rejected'});
  assert.equal(calls,0);
});

test('reported synchronous/async refresh errors preserve receipt; obsolete scope performs no refresh',async()=>{
  for(const onReceived of [()=>{throw Error('PRIVATE_REFRESH');},async()=>{throw Error('PRIVATE_REFRESH');}]){
    const result=await submitPestCapture(bodyFor(),{send:async()=>Response.json(receipt(),{status:201}),onReceived});
    assert.equal(result.kind,'received');if(result.kind==='received')assert.equal(result.refreshFailed,true);
    assert.equal(JSON.stringify(result).includes('PRIVATE_REFRESH'),false);
  }
  let current=true,refreshes=0,complete!:(r:Response)=>void;
  const pending=submitPestCapture(bodyFor(),{send:async()=>new Promise<Response>(resolve=>{complete=resolve;}),
    isCurrent:()=>current,onReceived:()=>{refreshes++;}});
  current=false;complete(Response.json(receipt(),{status:201}));assert.equal((await pending).kind,'received');assert.equal(refreshes,0);
});

test('four-language guidance separates result/reason/action and retains explicit unresolved/refresh warnings',()=>{
  for(const language of ['ko','vi','th','zh-CN'] as PestLanguage[]){
    for(const kind of ['received','rejected','uncertain'] as const){
      const result=kind==='received'?{kind,sessionId:receipt().sessionId,pestCode:'MITE',refreshFailed:false}:{kind};
      const guidance=pestCaptureGuidance(result,language);
      for(const text of [guidance.title,guidance.reason,guidance.action])assert.ok(text.trim().length>0);
      assert.equal(guidance.refreshWarning,null);
    }
    assert.ok(pestCaptureGuidance({kind:'received',sessionId:receipt().sessionId,pestCode:'OTHER',refreshFailed:true},language).refreshWarning);
  }
  const ko=pestCaptureGuidance({kind:'received',sessionId:receipt().sessionId,pestCode:'MITE',refreshFailed:false},'ko');
  assert.match(ko.title,/AI 판독 대기/);assert.match(ko.reason,/진단 완료가 아닙니다/);assert.match(ko.reason,/처방이 아닙니다/);
  assert.match(pestCaptureGuidance({kind:'uncertain'},'ko').action,/다시 보내기 전에/);
});

// Synthetic event/hook harness only, not browser or live upload acceptance.
test('accepted photo receipt cannot become a failed upload when the refresh callback throws',async()=>{
  const values:unknown[]=[];let cursor=0;
  const effects=new Map<number,{deps:unknown[];cleanup?:()=>void}>();
  const hooks={
    state(initial:unknown){const i=cursor++;if(!(i in values))values[i]=initial;return[values[i],(v:unknown)=>{values[i]=v;}];},
    ref(initial:unknown){const i=cursor++;return values[i]??(values[i]={current:initial});},
    effect(run:()=>void|(()=>void),deps:unknown[]){const i=cursor++,old=effects.get(i);
      if(!old||deps.some((v,index)=>!Object.is(v,old.deps[index]))){old?.cleanup?.();effects.set(i,{deps,cleanup:run()||undefined});}},
  };
  const key='nongtoriCaptureGuidanceHooks';
  Object.defineProperty(globalThis,key,{configurable:true,value:hooks});
  const hook=registerHooks({
    resolve(specifier,context,next){if(specifier==='react'&&context.parentURL?.endsWith('/PestCaptureForm.tsx'))return{url:'test:capture-guidance-hooks',shortCircuit:true};return next(specifier,context);},
    load(url,context,next){if(url==='test:capture-guidance-hooks')return{format:'module',shortCircuit:true,source:
      `export const useState=v=>globalThis.${key}.state(v);export const useRef=v=>globalThis.${key}.ref(v);export const useLayoutEffect=(f,d)=>globalThis.${key}.effect(f,d);`};return next(url,context);},
  });
  const originalFetch=globalThis.fetch,OriginalFormData=globalThis.FormData;
  let resets=0,calls=0;
  const form={reset(){resets++;}};
  let rgbFile=new File(['SYNTHETIC'],'rgb.png',{type:'image/png'});
  globalThis.FormData=class extends OriginalFormData{constructor(){super();this.set('pestCode','MITE');this.set('rgbImage',rgbFile);}};
  globalThis.fetch=async()=>{calls++;return Response.json({sessionId:'a7ea25a0-9a42-4e92-980f-9467ccf9967e',pestCode:'MITE',processingStatus:'UPLOADED_AWAITING_MODEL'},{status:201});};
  try{
    const {PestCaptureForm}=await import('../app/components/PestCaptureForm');
    type Props=Parameters<typeof PestCaptureForm>[0];
    const render=(props:Props)=>{cursor=0;return PestCaptureForm(props) as ReactElement<{onSubmit:(e:FormEvent<HTMLFormElement>)=>Promise<void>}>;};
    const event={preventDefault(){},currentTarget:form} as unknown as FormEvent<HTMLFormElement>;
    const initial:Props={farmId:'farm-a',itemId:'item-a',language:'ko',onUploaded:()=>{throw Error('PRIVATE_REFRESH_STACK');}};
    const tree=render(initial);
    assert.match(renderToStaticMarkup(tree),/40MB/,'서버의 합계 제한을 접수 전에 안내해야 함');
    await tree.props.onSubmit(event);
    const result=values[0] as {kind:string;refreshFailed?:boolean};
    assert.notEqual(result.kind,'error','a successful server receipt must survive a refresh error');
    assert.equal(result.kind,'received');assert.equal(result.refreshFailed,true);
    assert.equal(resets,1);assert.equal(calls,1,'no automatic re-upload');
    assert.equal(JSON.stringify(values).includes('PRIVATE_REFRESH_STACK'),false);
    const html=renderToStaticMarkup(render(initial));
    assert.match(html,/AI 판독 대기/);assert.match(html,/진단 완료가 아닙니다/);assert.match(html,/재접수하지 말고/);
    assert.equal(html.includes('PRIVATE_REFRESH_STACK'),false);

    for(const change of ['none','farm','item','unmount','uncertain','rejected','scope-collision'] as const){
      values.length=0;effects.clear();calls=resets=0;let refreshes=0,complete!:(r:Response)=>void;
      let props:Props={farmId:'farm-a',itemId:'item-a',language:'ko',onUploaded:()=>{refreshes++;}};
      if(change==='scope-collision')props={...props,farmId:'farm:a',itemId:'item'};
      globalThis.fetch=async()=>{calls++;return new Promise<Response>(resolve=>{complete=resolve;});};
      const firstTree=render(props),pending=firstTree.props.onSubmit(event);
      await firstTree.props.onSubmit(event);assert.equal(calls,1,'same-context double submit must not post twice');
      if(change==='farm')props={...props,farmId:'farm-b'};
      if(change==='item')props={...props,itemId:'item-b'};
      if(change==='scope-collision')props={...props,farmId:'farm',itemId:'a:item'};
      if(change==='unmount'){for(const effect of effects.values())effect.cleanup?.();}else render(props);
      const sendingView=change==='unmount'?'':renderToStaticMarkup(render(props));
      complete(Response.json(change==='uncertain'||change==='rejected'?{error:'PRIVATE_ERROR'}:receipt(),{status:change==='uncertain'?503:change==='rejected'?422:201}));
      await pending;
      const same=change==='none'||change==='uncertain'||change==='rejected';
      if(change!=='unmount')for(const [tag,name]of [['select','pestCode'],['input','rgbImage'],['input','thermalImage']]){
        const control=sendingView.match(new RegExp('<'+tag+'[^>]*name="'+name+'"[^>]*>'))?.[0];
        assert.ok(control,'선택 컨트롤이 유지돼야 함: '+name);
        assert.equal(control.includes('disabled=""'),same,'전송 중 같은 입력만 잠금: '+change+'/'+name);
      }
      assert.equal(refreshes,change==='none'?1:0);assert.equal(resets,change==='none'?1:0);assert.equal(calls,1);
      if(change==='uncertain'){
        const raced=firstTree.props.onSubmit(event);
        assert.equal(calls,1,'uncertain latch must block a repeat before React commits the new state');
        await raced;
      }
      if(change!=='unmount'){
        const nextTree=render(props),view=renderToStaticMarkup(nextTree);
        for(const [tag,name]of [['select','pestCode'],['input','rgbImage'],['input','thermalImage']]){
          const control=view.match(new RegExp('<'+tag+'[^>]*name="'+name+'"[^>]*>'))?.[0];
          assert.ok(control);assert.equal(control.includes('disabled=""'),false,'응답 뒤 입력 잠금 해제: '+change+'/'+name);
        }
        assert.equal(view.includes('PRIVATE_ERROR'),false);
        if(!same)assert.equal(view.includes('AI 판독 대기'),false,'foreign-scope result must not appear');
        if(change==='uncertain'){
          assert.match(view,/저장 여부도 아직 알 수 없습니다/);assert.match(view,/<button disabled=""/);
          await nextTree.props.onSubmit(event);assert.equal(calls,1,'unknown upload must not be automatically resent');
        }
        if(change==='rejected'){
          assert.equal(view.includes('<button disabled=""'),false);
          globalThis.fetch=async()=>{calls++;return Response.json(receipt(),{status:201});};
          await nextTree.props.onSubmit(event);assert.equal(calls,2,'correctable rejection allows explicit retry');
          assert.equal(refreshes,1);assert.equal(resets,1);
        }
      }
    }
    values.length=0;effects.clear();calls=resets=0;
    rgbFile=new File(['SYNTHETIC'],'not-image.pdf',{type:'application/pdf'});
    await render(initial).props.onSubmit(event);
    assert.equal(calls,0,'명확한 형식 오류는 실제 접수 전에 중단');assert.equal(resets,0);
    assert.match(renderToStaticMarkup(render(initial)),/이미지 파일을 다시 선택/);
    rgbFile=new File(['SYNTHETIC'],'unknown.bin',{type:''});
    globalThis.fetch=async()=>{calls++;return Response.json(receipt(),{status:201});};
    await render(initial).props.onSubmit(event);assert.equal(calls,1,'빈 MIME은 서버 판단으로 위임');
  }finally{globalThis.fetch=originalFetch;globalThis.FormData=OriginalFormData;hook.deregister();Reflect.deleteProperty(globalThis,key);}
});
