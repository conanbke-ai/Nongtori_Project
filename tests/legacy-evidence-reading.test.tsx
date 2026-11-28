// Synthetic React callback/SSR checks only. No browser, accounts or external fetch.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {registerHooks} from 'node:module';
import {readFileSync} from 'node:fs';
import {renderToStaticMarkup} from 'react-dom/server';
import type {Language} from '../app/lib/i18n';
import {fieldEvidenceCodes} from '../app/features/pests/domain/scouting-policy';

let opened=false;
(globalThis as unknown as {readingHooks:unknown}).readingHooks={
  useState:()=>[opened,(next:boolean|((value:boolean)=>boolean))=>{opened=typeof next==='function'?next(opened):next;}],
};
registerHooks({
  resolve(specifier,context,next){
    if(specifier==='react'&&context.parentURL?.endsWith('/LegacyEvidenceReading.tsx'))return{url:'test:reading-react',shortCircuit:true};
    return next(specifier,context);
  },
  load(url,context,next){
    if(url==='test:reading-react')return{format:'module',source:'export const {useState}=globalThis.readingHooks;',shortCircuit:true};
    return next(url,context);
  },
});
const {LegacyEvidenceReading}=await import('../app/features/pests/presentation/LegacyEvidenceReading');
const {ScoutingHistoryPanel}=await import('../app/features/pests/presentation/ScoutingHistory');
type ButtonProps={'aria-expanded':boolean;onClick:()=>void};
const view=(code:string,language:Language='ko')=>LegacyEvidenceReading({code,language});
const button=(tree:ReturnType<typeof view>)=>tree.props.children[0].props as ButtonProps;

test('reading disclosure starts collapsed and toggles without fetch or write callbacks',()=>{
  const previous=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>{calls++;throw Error('UNEXPECTED_NETWORK');};
  try{
    opened=false;const initial=view('DIRECT_MITE_OR_EGG_CONFIRMED');
    assert.equal(button(initial)['aria-expanded'],false);
    assert.ok(!renderToStaticMarkup(initial).includes('DIRECT_MITE_OR_EGG_CONFIRMED'));
    button(initial).onClick();assert.equal(button(view('DIRECT_MITE_OR_EGG_CONFIRMED'))['aria-expanded'],true);
    button(view('DIRECT_MITE_OR_EGG_CONFIRMED')).onClick();assert.equal(opened,false);assert.equal(calls,0);
  }finally{globalThis.fetch=previous;}
});

test('every known code displays original and derived provenance without confidence or negative diagnosis',()=>{
  opened=true;
  for(const code of fieldEvidenceCodes){
    const html=renderToStaticMarkup(view(code));
    assert.ok(html.includes(code));assert.ok(html.includes('원문 코드'));
    assert.ok(html.includes('기존 기록에서 해석됨'));assert.ok(html.includes('새 진단이나 확정 음성 판정이 아닙니다.'));
    assert.ok(html.includes('LEGACY_FIELD_EVIDENCE_V1'));assert.ok(!html.includes('99%'));
    assert.equal(html.includes('SPIDER_MITE'),code==='DIRECT_MITE_OR_EGG_CONFIRMED');
  }
});

test('unknown code remains exact escaped text, not an inferred species, executable markup or raw metadata',()=>{
  opened=true;
  const code='<script>alert("SYNTHETIC")</script>';
  const html=renderToStaticMarkup(view(code));
  assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));
  assert.ok(html.includes('해석 규칙에 없는 코드'));assert.ok(!html.includes('SPIDER_MITE'));
  const alias=renderToStaticMarkup(view('MITE '));assert.ok(alias.includes('MITE '));assert.ok(alias.includes('해석 규칙에 없는 코드'));
  assert.ok(renderToStaticMarkup(view('')).includes('(빈 코드)'));
});

test('four locales distinguish source/derived reading and styles retain touch/focus/long-code safeguards',()=>{
  opened=true;
  const labels=['원문 코드','Mã gốc','รหัสต้นฉบับ','原始代码'];
  for(const [i,language]of (['ko','vi','th','zh-CN'] as Language[]).entries()){
    const html=renderToStaticMarkup(view('NO_VISIBLE_EVIDENCE',language));assert.ok(html.includes(labels[i]));
    assert.ok(html.includes('aria-expanded="true"'));assert.ok(!html.includes('SPIDER_MITE'));
  }
  const css=readFileSync('app/features/pests/presentation/scouting-history.css','utf8');
  assert.ok(css.includes('.scouting-legacy-reading button { min-height: 44px; }'));
  assert.ok(css.includes('overflow-wrap: anywhere'));assert.ok(css.includes('button:focus-visible'));
});

test('history attaches reading only to already-projected field checks, retaining stale/error and correction semantics',()=>{
  opened=false;
  const entries=[
    {kind:'fieldChecks' as const,id:'original',at:null,code:'INCONCLUSIVE',originalCheckId:null,replacementCode:null},
    {kind:'corrections' as const,id:'correction',at:null,code:'VOID',originalCheckId:'original',replacementCode:null},
    {kind:'actions' as const,id:'action',at:null,code:'OBSERVE_ONLY',originalCheckId:null,replacementCode:null},
  ];
  const panel=(status:'ready'|'stale'|'error')=>renderToStaticMarkup(<ScoutingHistoryPanel language="ko" onRetry={()=>{}} state={{scope:'s',status,entries:status==='error'?[]:entries}} />);
  assert.equal((panel('ready').match(/기록 해석 출처/g)??[]).length,1);
  assert.ok(panel('ready').includes('href="#scouting-history-check-original"'));
  assert.ok(panel('stale').includes('이전 조회 결과'));assert.ok(!panel('error').includes('기록 해석 출처'));
  const before=JSON.stringify(entries);panel('ready');assert.equal(JSON.stringify(entries),before);
});
