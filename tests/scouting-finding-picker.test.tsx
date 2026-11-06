// Synthetic component callbacks + fresh in-memory API binding. Not browser acceptance.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import type { Language } from '../app/lib/i18n';
import { fieldEvidenceCodes } from '../app/features/pests/domain/scouting-policy';
import { scoutingIntentFixture } from './support/scouting-idempotency-fixture';
import { testIdentityProvider } from './support/test-identity-provider';
import { POST } from '../app/api/scouting-field-checks/route';

let state: unknown = null;
(globalThis as unknown as { findingHooks: unknown }).findingHooks = {
  useState: () => [state, (next: unknown) => { state = next; }],
};
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react' && context.parentURL?.endsWith('/ScoutingFindingPicker.tsx')) return { url:'test:finding-react',shortCircuit:true };
    return next(specifier,context);
  },
  load(url,context,next) {
    if (url === 'test:finding-react') return { format:'module',source:'export const {useState}=globalThis.findingHooks;',shortCircuit:true };
    return next(url,context);
  },
});
const { ScoutingFindingPicker, findingGroups } = await import('../app/features/pests/presentation/ScoutingFindingPicker');
type Element = { type: unknown; props: { children?: unknown; disabled?: boolean; onClick?: () => void; 'aria-pressed'?: boolean; 'aria-label'?: string } };
function buttons(node: unknown): Element[] {
  if (Array.isArray(node)) return node.flatMap(buttons);
  if (!node || typeof node !== 'object' || !('type' in node)) return [];
  const element = node as Element;
  return [...(element.type === 'button' ? [element] : []), ...buttons(element.props.children)];
}
const options = fieldEvidenceCodes.map(code => ({code,label:code}));
const scope = JSON.stringify(['farm-a','loc']);

test('group selection is unsaved and exposes every existing evidence exactly once without defaults', () => {
  state = null; const selected: string[] = [];
  const render = () => ScoutingFindingPicker({scope,language:'ko',options,disabled:false,onSelect:code=>selected.push(code)});
  assert.equal(buttons(render()).length,4); assert.equal(selected.length,0);
  const flattened = Object.values(findingGroups).flat();
  assert.deepEqual([...flattened].sort(),[...fieldEvidenceCodes].sort());
  assert.equal(new Set(flattened).size,8);
  for (const [index,codes] of Object.values(findingGroups).entries()) {
    const beforeSelection: number = selected.length;
    buttons(render())[index].props.onClick!();
    assert.equal(selected.length,beforeSelection);
    const visible = buttons(render());
    assert.equal(visible[index].props['aria-pressed'],true);
    assert.deepEqual(visible.slice(4).map(b=>b.props.children),codes);
    for (const button of visible.slice(4)) button.props.onClick!();
  }
  assert.deepEqual(selected,flattened);
});

test('disabled controls cannot select/submit and changing farm or location hides previous selection', () => {
  state = null; const selected: string[] = [];
  const render = (target=scope,disabled=false) => ScoutingFindingPicker({scope:target,language:'ko',options,disabled,onSelect:code=>selected.push(code)});
  for(const button of buttons(render(scope,true))) { assert.equal(button.props.disabled,true);button.props.onClick!(); }
  assert.equal(state,null);assert.equal(selected.length,0);
  buttons(render())[1].props.onClick!();assert.equal(buttons(render()).length,8);
  for(const button of buttons(render(scope,true))) { assert.equal(button.props.disabled,true);button.props.onClick!(); }
  assert.equal(selected.length,0);
  assert.equal(buttons(render(JSON.stringify(['farm-a','other']))).length,4);
  assert.equal(buttons(render(JSON.stringify(['farm-b','loc']))).length,4);
});

test('four-language group labels use button semantics and never invoke fetch on selection', () => {
  const before=globalThis.fetch; let calls=0;
  globalThis.fetch=async()=>{calls++;throw Error('UNEXPECTED_FETCH');};
  try {
    const titles=['관찰한 내용 선택','Chọn nội dung quan sát','เลือกสิ่งที่สังเกต','选择观察内容'];
    for(const [i,language] of (['ko','vi','th','zh-CN'] as Language[]).entries()) {
      state=null;
      const view=ScoutingFindingPicker({scope,language,options,disabled:false,onSelect:()=>assert.fail('Group must not submit')});
      assert.equal((view.props.children[1] as Element).props['aria-label'],titles[i]);
      for(const button of buttons(view))button.props.onClick!();
    }
    assert.equal(calls,0);
  } finally {globalThis.fetch=before;}
});

test('each selected legacy code reaches real authorized POST and retains its original stored meaning', async () => {
  for(const codes of Object.values(findingGroups)) for(const code of codes) {
    const f=scoutingIntentFixture();
    (globalThis as unknown as {nongtoriTestEnv:unknown}).nongtoriTestEnv=f.env;
    try {
      const post=(actor:'worker-a'|'owner-b',key:string)=>POST(testIdentityProvider.requestAs(actor,'/api/scouting-field-checks',{
        method:'POST',headers:{'content-type':'application/json','Idempotency-Key':key},
        body:JSON.stringify({farmId:'farm-a',locationStateId:'loc',evidenceCode:code}),
      }));
      const denied=await post('owner-b',crypto.randomUUID());assert.equal(denied.status,403);
      assert.equal(f.sqlite.prepare('SELECT COUNT(*) n FROM scouting_field_checks').get()!.n,0);
      const result=await post('worker-a',crypto.randomUUID());assert.equal(result.status,201);
      const row=f.sqlite.prepare('SELECT primary_evidence_code FROM scouting_field_checks').get();
      assert.equal(row!.primary_evidence_code,code);
    } finally {f.sqlite.close();}
  }
});

test('queue keeps existing review boundary, farm/location key and unchanged evidence callback', () => {
  const source=readFileSync('app/features/pests/presentation/ScoutingQueue.tsx','utf8');
  assert.ok(source.includes('{canReview && <div className="scouting-detail-actions">'));
  assert.ok(source.includes('<ScoutingFindingPicker key={JSON.stringify([farmId, selected.id])}'));
  assert.ok(source.includes('onSelect={code => void submitFieldCheck(selected, code)}'));
  assert.ok(source.includes('disabled={Boolean(sending)}'));
});
