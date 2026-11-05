// Synthetic React hooks exercise actual component callbacks, not browser acceptance.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHooks } from 'node:module';
import type { ReactElement } from 'react';

type Effect = { dependencies: unknown[]; cleanup?: () => void };
const values: unknown[] = [], effects: Effect[] = [];
let cursor = 0;
const hooks = {
  useState(initial: unknown) {
    const i = cursor++;
    if (!(i in values)) values[i] = typeof initial === 'function' ? initial() : initial;
    return [values[i], (value: unknown) => { values[i] = value; }];
  },
  useLayoutEffect(create: () => (() => void), dependencies: unknown[]) {
    const i = cursor++, previous = effects[i];
    if (!previous || dependencies.some((v, j) => v !== previous.dependencies[j])) {
      previous?.cleanup?.(); effects[i] = { dependencies, cleanup: create() };
    }
  },
};
(globalThis as unknown as { originalHooks: unknown }).originalHooks = hooks;
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'react' && context.parentURL?.endsWith('/ScoutingOriginalCheck.tsx')) return { url: 'test:original-react', shortCircuit: true };
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === 'test:original-react') return { format:'module', source:'export const {useState,useLayoutEffect} = globalThis.originalHooks;', shortCircuit:true };
    return next(url,context);
  },
});

test('actual original component click, context switch and cleanup keep pending results scoped', async () => {
  const previousFetch = globalThis.fetch;
  const pending: ((r: Response) => void)[] = [];
  globalThis.fetch = async () => new Promise<Response>(resolve => pending.push(resolve));
  try {
    const { ScoutingOriginalCheck } = await import('../app/features/pests/presentation/ScoutingOriginalCheck');
    const render = (locationId = 'loc', farmId = 'farm-a') => {
      cursor = 0;
      return ScoutingOriginalCheck({farmId,locationId,checkId:'check-0',language:'ko',labelForCode:()=> '원본 판정'});
    };
    const button = (element: ReactElement) => (element.props as { children: ReactElement[] }).children[0].props as { onClick: () => void; disabled: boolean };
    const payload = (farm_id = 'farm-a', location_state_id = 'loc') => Response.json({original:{id:'check-0',farm_id,location_state_id,primary_evidence_code:'INCONCLUSIVE',checked_at:'2026-01-01T00:00:00Z'}});
    assert.equal(pending.length,0); const initial = render(); assert.equal(pending.length,0);
    button(initial).onClick(); button(initial).onClick(); assert.equal(pending.length,1);
    assert.equal(button(render()).disabled,true);
    const switched = render('other','farm-b'); assert.equal(button(switched).disabled,false);
    pending[0](payload()); await new Promise(resolve => setImmediate(resolve));
    assert.equal((values[1] as {status:string}).status,'loading'); // late success never publishes ready
    button(render('other','farm-b')).onClick(); assert.equal(pending.length,2);
    pending[1](payload('farm-b','other')); await new Promise(resolve => setImmediate(resolve));
    assert.equal((values[1] as {status:string}).status,'ready');
    button(render('other','farm-b')).onClick();
    effects.forEach(effect => effect?.cleanup?.()); const before = values[1];
    pending[2](new Response('',{status:404})); await new Promise(resolve => setImmediate(resolve));
    assert.equal(values[1],before);
  } finally { effects.forEach(effect => effect?.cleanup?.()); globalThis.fetch = previousFetch; }
});
