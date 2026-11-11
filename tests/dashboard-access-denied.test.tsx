// Synthetic hooks reuse the existing lifecycle-fixture approach. Actual production
// callbacks run; this is not React reconciliation, DOM, network or browser acceptance.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { registerHooks } from 'node:module';
import { renderToStaticMarkup } from 'react-dom/server';
import type { ReactElement, ReactNode } from 'react';
import type { Language } from '../app/lib/i18n';

type Props = Record<string, unknown>;
type Element = ReactElement<Props>;
type Effect = { deps: unknown[]; cleanup?: () => void };
type State = { value: unknown };
function harness() {
  const states: State[] = [], refs: { current: unknown }[] = [], effects: Effect[] = [], callbacks: { fn: unknown; deps: unknown[] }[] = [];
  let si = 0, ri = 0, ei = 0, ci = 0;
  const tasks: { layout: boolean; run: () => void }[] = [];
  return {
    states, refs,
    reset() { si = ri = ei = ci = 0; },
    state(initial: unknown) {
      const box = states[si++] ?? (states[si - 1] = { value: typeof initial === 'function' ? initial() : initial });
      return [box.value, (value: unknown) => { box.value = typeof value === 'function' ? value(box.value) : value; }];
    },
    ref(initial: unknown) { return refs[ri++] ?? (refs[ri - 1] = { current: initial }); },
    effect(create: () => void | (() => void), deps: unknown[], layout = false) {
      const index = ei++, previous = effects[index];
      if (!previous || deps.some((v, i) => !Object.is(v, previous.deps[i]))) tasks.push({ layout, run: () => {
        previous?.cleanup?.(); effects[index] = { deps, cleanup: create() || undefined };
      } });
    },
    callback(fn: unknown, deps: unknown[]) {
      const index = ci++, previous = callbacks[index];
      if (!previous || deps.some((v, i) => !Object.is(v, previous.deps[i]))) callbacks[index] = { fn, deps };
      return callbacks[index].fn;
    },
    commit() { for (const task of tasks.splice(0).sort((a, b) => Number(b.layout) - Number(a.layout))) task.run(); },
    cleanup() { for (const effect of effects) effect?.cleanup?.(); },
  };
}
let active: ReturnType<typeof harness>;
Object.defineProperty(globalThis, 'dashboard403Hooks', { configurable: true, get: () => active });
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('@/') && specifier.endsWith('.css')) return { url: new URL('../' + specifier.slice(2), import.meta.url).href, shortCircuit: true };
    if (specifier === 'react' && /\/(FarmerDashboard|PestAlertReview|ScoutingQueue)\.tsx$/.test(context.parentURL ?? '')) return { url: 'test:dashboard403-hooks', shortCircuit: true };
    return next(specifier, context);
  },
  load(url, context, next) {
    if (url === 'test:dashboard403-hooks') return { format: 'module', shortCircuit: true, source:
      'const h=()=>globalThis.dashboard403Hooks;export const useState=v=>h().state(v);export const useRef=v=>h().ref(v);export const useEffect=(f,d)=>h().effect(f,d);export const useLayoutEffect=(f,d)=>h().effect(f,d,true);export const useMemo=f=>f();export const useCallback=(f,d)=>h().callback(f,d);' };
    return next(url, context);
  },
});
const { FarmerDashboard } = await import('../app/components/FarmerDashboard');
const { PestAlertReview } = await import('../app/components/PestAlertReview');
const { FarmMiniChat } = await import('../app/components/FarmMiniChat');
const { ScoutingQueue } = await import('../app/features/pests/presentation/ScoutingQueue');
const { ScoutingFindingPicker } = await import('../app/features/pests/presentation/ScoutingFindingPicker');
const { ScoutingPendingIntent } = await import('../app/features/pests/presentation/scouting-pending-intent');

function nodes(node: ReactNode): Element[] {
  if (Array.isArray(node)) return node.flatMap(nodes);
  if (!node || typeof node !== 'object' || !('props' in node)) return [];
  const element = node as Element;
  return [element, ...nodes(element.props.children as ReactNode)];
}
function one(tree: ReactNode, predicate: (node: Element) => boolean) { const node = nodes(tree).find(predicate); assert.ok(node); return node; }
function call(node: Element, name = 'onClick', argument?: unknown) { const fn = node.props[name]; assert.equal(typeof fn, 'function'); return (fn as (arg?: unknown) => unknown)(argument); }
const flush = () => new Promise<void>(resolve => setImmediate(resolve));
type Pending = { url: string; method: string; resolve: (response: Response) => void; reject: (error: Error) => void };
async function fixture(run: (f: { render: () => Element; pending: Pending[]; snapshot: (farm?: string) => Record<string, unknown>; denied: () => boolean; refresh: () => void; h: ReturnType<typeof harness> }) => Promise<void>, screen = 'alerts', explicitPostCount = 0, preferredLanguage: Language = 'ko') {
  const previousFetch = globalThis.fetch, previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window'), previousDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  active = harness(); const h = active, pending: Pending[] = [];
  const location = { href: `http://synthetic.invalid/?screen=${screen}`, search: `?screen=${screen}` };
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    location, localStorage: { getItem: () => null, setItem: () => {} }, scrollY: 0, innerHeight: 900,
    setTimeout: (fn: () => void) => { fn(); return 1; }, clearTimeout() {}, addEventListener() {}, removeEventListener() {}, scrollTo() {},
    history: { replaceState() {}, pushState() {} }, matchMedia: () => ({ matches: true }),
  } });
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { documentElement: { scrollHeight: 900 } } });
  globalThis.fetch = async (url, init) => new Promise<Response>((resolve, reject) => pending.push({ url: String(url), method: init?.method ?? 'GET', resolve, reject }));
  const render = () => { active = h; h.reset(); const tree = FarmerDashboard() as Element; h.commit(); return tree; };
  render(); await flush();
  const empty = h.states.map(s => s.value).find(v => v && typeof v === 'object' && 'farms' in v && 'account' in v) as Record<string, unknown>;
  function snapshot(farm = 'farm-a') {
    const data = structuredClone(empty), farms = [{ id: 'farm-a', name: 'SYNTHETIC_A', timezone: 'Asia/Seoul' }, { id: 'farm-b', name: 'SYNTHETIC_B', timezone: 'Asia/Seoul' }];
    data.farms = farms; data.selectedFarm = farms.find(f => f.id === farm);
    data.account = { ...(data.account as Props), memberId: farm + '-member', authenticated: true, publicName: 'SYNTHETIC_MEMBER', preferredLanguage, role: 'OWNER', permissions: { viewHistory: true, reviewAlerts: true, viewRevenue: false } };
    data.items = [{ id: farm + '-item', crop_code: 'STRAWBERRY', crop_name: '딸기', cultivar_code: 'SEOLHYANG', cultivar_name: '설향', display_name: 'SYNTHETIC_ITEM', crop_image_uri: null, crop_description: null }];
    return data;
  }
  const initial = snapshot(); pending[0].resolve(Response.json(initial)); await flush(); render(); await flush();
  try { await run({ render, pending, snapshot, h,
    denied: () => one(render(), n => 'data-private-dashboard' in n.props).props.hidden === true,
    refresh: () => { call(one(render(), n => n.props.className === 'refresh-button')); },
  }); assert.equal(pending.filter(p => p.method !== 'GET').length, explicitPostCount, 'only the explicitly invoked mutation callbacks may write'); }
  finally { h.cleanup(); globalThis.fetch = previousFetch;
    if (previousWindow) Object.defineProperty(globalThis, 'window', previousWindow); else Reflect.deleteProperty(globalThis, 'window');
    if (previousDocument) Object.defineProperty(globalThis, 'document', previousDocument); else Reflect.deleteProperty(globalThis, 'document');
  }
}

test('actual dashboard 403 hides/inerts retained private tree, including chat and portal host, without consuming denied body', async () => {
  await fixture(async f => {
    const before = f.render(), oldReview = one(before, n => n.type === PestAlertReview), original = JSON.stringify(f.snapshot());
    f.refresh(); let bodyReads = 0;
    const response = new Response('SYNTHETIC_DENIED_BODY', { status: 403 }); response.json = async () => { bodyReads++; throw Error('must not be consumed for UI status handling'); };
    f.pending.at(-1)!.resolve(response); await flush();
    const tree = f.render(), gate = one(tree, n => 'data-private-dashboard' in n.props), panel = one(tree, n => n.props.className === 'dashboard-access-denied module-workspace');
    assert.equal(gate.props.hidden, true); assert.equal(gate.props.inert, true); assert.equal(bodyReads, 0);
    assert.ok(nodes(gate).some(n => n.props.className === 'app-topbar')); assert.ok(nodes(gate).some(n => n.type === FarmMiniChat));
    const review = one(gate, n => n.type === PestAlertReview); assert.equal(review.key, oldReview.key); assert.equal(review.props.readBlocked, true);
    assert.ok(renderToStaticMarkup(panel).includes('사용 권한 다시 확인')); assert.ok(!renderToStaticMarkup(panel).includes('SYNTHETIC_ITEM'));
    assert.equal(JSON.stringify(f.snapshot()), original, 'source fixture is immutable');
  });
});

test('미종료 403 본문에서도 private scope를 차단하고 이전 조회가 복구하지 못한다', async () => {
  await fixture(async f => {
    f.refresh(); const oldRequest = f.pending.at(-1)!;
    f.refresh(); let cancelled = false;
    // 생산자는 close/error를 호출하지 않습니다. 본문 완료를 기다리는 구현이면 실패해야 합니다.
    const response = new Response(new ReadableStream<Uint8Array>({ cancel() { cancelled = true; } }), { status: 403 });
    try {
      f.pending.at(-1)!.resolve(response); await flush();
      const gate = one(f.render(), n => 'data-private-dashboard' in n.props);
      assert.equal(gate.props.hidden, true); assert.equal(gate.props.inert, true);
      assert.equal(response.bodyUsed, false); assert.equal(response.body?.locked, false); assert.equal(cancelled, false);
      oldRequest.resolve(Response.json(f.snapshot('farm-b'))); await flush();
      assert.equal(f.denied(), true, '이전 조회 성공은 명시적 권한 재확인이 아님');
      assert.equal(response.bodyUsed, false); assert.equal(response.body?.locked, false);
    } finally {
      await response.body?.cancel('합성 회귀 종료');
      assert.equal(cancelled, true);
    }
  });
});

test('권한 복구 패널은 기존 네 언어와 대기·실패·정상 복귀를 유지한다', async () => {
  const expected = {
    vi: ['Không thể hiển thị thông tin nông trại này.', 'Nông trại cần kiểm tra lại', 'Kiểm tra lại quyền truy cập', 'Đang kiểm tra quyền truy cập', 'Chưa kiểm tra lại được. Hãy thử lại hoặc chọn nông trại khác.'],
    th: ['ไม่สามารถแสดงข้อมูลฟาร์มนี้ได้', 'ฟาร์มที่ต้องการตรวจสอบอีกครั้ง', 'ตรวจสอบสิทธิ์อีกครั้ง', 'กำลังตรวจสอบสิทธิ์', 'ยังตรวจสอบไม่ได้ โปรดลองอีกครั้งหรือเลือกฟาร์มอื่น'],
    'zh-CN': ['无法显示此农场的信息。', '要重新确认的农场', '重新确认访问权限', '正在确认访问权限', '暂时无法重新确认。请重试或选择其他农场。'],
    ko: ['이 농장 정보를 표시할 수 없습니다.', '다시 확인할 농장', '사용 권한 다시 확인', '권한 확인 중', '다시 확인하지 못했습니다. 다시 시도하거나 다른 농장을 선택해 주세요.'],
  };
  for (const [language, text] of Object.entries(expected)) await fixture(async f => {
    f.refresh(); f.pending.at(-1)!.resolve(new Response('', { status: 403 })); await flush();
    const panel = () => one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    assert.equal(panel().props.lang, language);
    assert.equal(one(panel(), n => n.type === 'h1').props.children, text[0]);
    assert.equal(one(panel(), n => n.type === 'select').props['aria-label'], text[1]);
    assert.equal(one(panel(), n => n.type === 'button').props.children, text[2]);
    call(one(panel(), n => n.type === 'button')); await flush();
    assert.equal(one(panel(), n => n.type === 'button').props.disabled, true);
    assert.equal(one(panel(), n => n.type === 'select').props.disabled, true);
    assert.equal(one(panel(), n => n.type === 'button').props.children, text[3]);
    assert.equal(f.denied(), true);
    f.pending.at(-1)!.resolve(new Response('', { status: 503 })); await flush();
    assert.ok(renderToStaticMarkup(panel()).includes(text[4]));
    assert.equal(one(panel(), n => n.type === 'button').props.disabled, false);
    assert.equal(f.denied(), true);
    call(one(panel(), n => n.type === 'button'));
    const current = f.snapshot(); (current.account as Props).preferredLanguage = language;
    f.pending.at(-1)!.resolve(Response.json(current)); await flush();
    assert.equal(f.denied(), false, '현재 사용자의 명시적 정상 재확인으로만 복귀');
  }, 'alerts', 0, language as Language);
});

test('actual dashboard transient 503 and network errors retain the normal stale scope', async () => {
  for (const error of ['503', 'network']) await fixture(async f => {
    f.refresh(); const request = f.pending.at(-1)!;
    if (error === '503') request.resolve(new Response('', { status: 503 })); else request.reject(TypeError('SYNTHETIC_OFFLINE'));
    await flush(); assert.equal(f.denied(), false);
    const banner = one(f.render(), n => n.props.className === 'error-banner');
    assert.ok(renderToStaticMarkup(banner).includes('마지막으로 불러온 정보'));
  });
});

test('repeat 403/503 stay blocked; automatic child refresh cannot reopen, only explicit success restores', async () => {
  await fixture(async f => {
    const automatic = one(f.render(), n => n.type === PestAlertReview);
    f.refresh(); f.pending.at(-1)!.resolve(new Response('', { status: 403 })); await flush(); assert.ok(f.denied());
    const count = f.pending.length;
    call(automatic, 'onReviewed'); await flush(); assert.equal(f.pending.length, count);
    for (const status of [403, 503]) {
      const panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
      call(one(panel, n => n.type === 'button')); assert.ok(f.denied(), 'pending retry is not permission approval');
      f.pending.at(-1)!.resolve(new Response('', { status })); await flush(); assert.ok(f.denied());
    }
    const panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    call(one(panel, n => n.type === 'button')); f.pending.at(-1)!.resolve(Response.json(f.snapshot())); await flush(); assert.equal(f.denied(), false);
  });
});

test('denied recovery stages another farm without replacing private owners until a successful snapshot', async () => {
  for (const status of [403, 503]) await fixture(async f => {
    const oldReview = one(f.render(), n => n.type === PestAlertReview);
    f.refresh(); f.pending.at(-1)!.resolve(new Response('', { status: 403 })); await flush(); assert.ok(f.denied());
    let panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    call(one(panel, n => n.type === 'select'), 'onChange', { target: { value: 'farm-b' } });
    assert.equal(one(f.render(), n => n.type === PestAlertReview).key, oldReview.key);
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.farmId, 'farm-a');
    f.pending.at(-1)!.resolve(new Response('', { status })); await flush(); assert.ok(f.denied());
    const retained = one(f.render(), n => n.type === PestAlertReview);
    assert.equal(retained.key, oldReview.key); assert.equal(retained.props.farmId, 'farm-a');
    panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    assert.equal(one(panel, n => n.type === 'select').props.value, 'farm-b');
    call(one(panel, n => n.type === 'button')); assert.ok(f.pending.at(-1)!.url.includes('farmId=farm-b'));
    f.pending.at(-1)!.resolve(Response.json(f.snapshot('farm-b'))); await flush(); assert.equal(f.denied(), false);
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.farmId, 'farm-b');
  });
});

test('older dashboard success/error cannot clear a later 403 or overwrite an explicitly recovered other farm', async () => {
  for (const late of ['success', 'error']) for (const arrival of ['blocked', 'recovered']) await fixture(async f => {
    f.refresh(); const old = f.pending.at(-1)!; f.refresh(); f.pending.at(-1)!.resolve(new Response('', { status: 403 })); await flush(); assert.ok(f.denied());
    const finishOld = () => { if (late === 'success') old.resolve(Response.json(f.snapshot())); else old.reject(Error('SYNTHETIC_OLD_ERROR')); };
    if (arrival === 'blocked') { finishOld(); await flush(); assert.ok(f.denied()); }
    const panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    call(one(panel, n => n.type === 'select'), 'onChange', { target: { value: 'farm-b' } });
    f.pending.at(-1)!.resolve(Response.json(f.snapshot('farm-b'))); await flush(); assert.equal(f.denied(), false);
    if (arrival === 'recovered') { finishOld(); await flush(); assert.equal(f.denied(), false); }
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.farmId, 'farm-b');
  });
});

test('late operation-history success/error is invalidated by 403 and cannot overwrite same-farm recovery', async () => {
  for (const outcome of ['success', 'error']) await fixture(async f => {
    const old = f.pending.find(p => p.url.startsWith('/api/operation-history')); assert.ok(old);
    f.refresh(); f.pending.filter(p => p.url.startsWith('/api/farmer-dashboard')).at(-1)!.resolve(new Response('', { status: 403 })); await flush(); assert.ok(f.denied());
    const panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace');
    call(one(panel, n => n.type === 'button')); f.pending.at(-1)!.resolve(Response.json(f.snapshot())); await flush(); f.render(); await flush();
    const current = f.pending.filter(p => p.url.startsWith('/api/operation-history')).at(-1)!; assert.notEqual(current, old);
    current.resolve(Response.json({ rows: [], total: 0, page: 1, limit: 30, pageCount: 0 })); await flush();
    const stateBefore = JSON.stringify(f.h.states.map(s => s.value));
    if (outcome === 'success') old.resolve(Response.json({ rows: [{ id: 'SYNTHETIC_OLD_PRIVATE' }], total: 1, page: 1, limit: 30, pageCount: 1 })); else old.reject(Error('SYNTHETIC_OLD_ERROR'));
    await flush(); assert.equal(JSON.stringify(f.h.states.map(s => s.value)), stateBefore); assert.equal(f.denied(), false);
  }, 'history');
});

test('explicit no-farm snapshot retains existing scope-cancellation meaning without global logout', async () => {
  await fixture(async f => {
    f.refresh(); f.pending.at(-1)!.resolve(new Response('', { status: 403 })); await flush(); assert.ok(f.denied());
    const panel = one(f.render(), n => n.props.className === 'dashboard-access-denied module-workspace'); call(one(panel, n => n.type === 'button'));
    const next = f.snapshot(); next.farms = []; next.selectedFarm = null; next.items = [];
    f.pending.at(-1)!.resolve(Response.json(next)); await flush(); assert.equal(f.denied(), false);
    const tree = f.render(); assert.equal(nodes(tree).some(n => n.type === PestAlertReview && n.props.farmId), false);
    assert.ok(f.h.states.some(s => s.value && typeof s.value === 'object' && 'account' in s.value && (s.value.account as Props).authenticated === true));
  });
});

test('dashboard cleanup cancels late success or denial without altering retained state', async () => {
  for (const status of [200, 403]) await fixture(async f => {
    f.refresh(); const pending = f.pending.at(-1)!; f.h.cleanup(); const before = JSON.stringify(f.h.states);
    pending.resolve(status === 200 ? Response.json(f.snapshot()) : new Response('', { status })); await flush();
    assert.equal(JSON.stringify(f.h.states), before);
  });
});

test('actual queue read revocation rejects late reads and preserves the mounted uncertain request key', async () => {
  for (const outcome of ['success', 'error']) await fixture(async f => {
    const dashboardHooks = active, q = harness(); let blocked = false, readEpoch = 0; active = q;
    const render = () => { active = q; q.reset(); const tree = ScoutingQueue({ farmId: 'farm-a', canReview: true, language: 'ko', keyedMutations: true, mutationMemberId: 'member-a', readBlocked: blocked, readEpoch }); q.commit(); return tree; };
    try {
      const before = render(); await flush(); const late = f.pending.at(-1)!; assert.ok(late.url.startsWith('/api/scouting-locations'));
      const oldReadTrigger = one(before, n => n.type === 'button');
      let keys = 0;
      const client = new ScoutingPendingIntent(async () => { throw Error('SYNTHETIC_RESPONSE_LOSS'); }, () => { keys++; return '00000000-0000-4000-8000-000000000001'; });
      await assert.rejects(client.request('/api/scouting-field-checks', { farmId: 'farm-a', locationStateId: 'loc', evidenceCode: 'NO_VISIBLE_EVIDENCE' }, 'member-a'), /SYNTHETIC_RESPONSE_LOSS/);
      const intent = client.snapshot(), clientRef = q.refs.find(r => r.current === null)!; clientRef.current = client;
      const pendingState = q.states.at(-1)!; pendingState.value = intent;
      blocked = true; readEpoch++; render(); await flush(); const calls = f.pending.length;
      call(oldReadTrigger); await flush(); assert.equal(f.pending.length, calls, 'old closures cannot restart a denied read');
      if (outcome === 'success') late.resolve(Response.json({ rows: [{ id: 'SYNTHETIC_OLD_PRIVATE' }] })); else late.reject(Error('SYNTHETIC_OLD_ERROR'));
      await flush(); render();
      assert.equal(q.states.some(s => Array.isArray(s.value) && s.value.some(v => v.id === 'SYNTHETIC_OLD_PRIVATE')), false);
      assert.equal(f.pending.length, calls); assert.equal(client.snapshot()?.key, intent?.key); assert.deepEqual(client.snapshot(), intent); assert.equal(keys, 1);
      assert.equal(clientRef.current, client); assert.deepEqual(pendingState.value, intent);
      const pendingPanel = one(render(), n => n.props.className === 'scouting-correction-panel');
      assert.ok(nodes(pendingPanel).some(n => n.type === 'button' && n.props.children === '같은 키로 저장 재시도'));
      blocked = false; render(); await flush(); assert.equal(f.pending.length, calls + 1, 'read recovery does not retry mutation');
      call(oldReadTrigger); await flush(); assert.equal(f.pending.length, calls + 1, 'old pre-denial callback stays obsolete even after recovery');
      assert.deepEqual(client.snapshot(), intent); assert.equal(keys, 1);
      assert.equal(clientRef.current, client); assert.deepEqual(pendingState.value, intent);
    } finally { q.cleanup(); active = dashboardHooks; }
  });
});

test('validated member ID reaches the actual review and queue props without enabling keyed mutations', async () => {
  await fixture(async f => {
    const review = one(f.render(), n => n.type === PestAlertReview);
    assert.equal(review.props.mutationMemberId, 'farm-a-member');
    assert.equal(review.props.keyedMutations, undefined);
    const parent = active, child = harness(); active = child;
    try {
      child.reset();
      const tree = PestAlertReview(review.props as Parameters<typeof PestAlertReview>[0]); child.commit();
      const queue = one(tree, n => n.type === ScoutingQueue);
      assert.equal(queue.props.mutationMemberId, 'farm-a-member');
      assert.equal(queue.props.keyedMutations, undefined, 'do not activate from member presence');
      const q = harness(); active = q; q.reset();
      const rendered = ScoutingQueue(queue.props as Parameters<typeof ScoutingQueue>[0]); q.commit(); await flush();
      assert.equal(nodes(rendered).some(n => n.props.children === '저장 결과만 조회'), false);
      assert.equal(q.refs.some(ref => ref.current instanceof ScoutingPendingIntent), false, 'no client/key created on render');
      q.cleanup();
    } finally { child.cleanup(); active = parent; }
  });
});

test('optimistic farm selection never passes the previous snapshot member to the new farm', async () => {
  await fixture(async f => {
    const select = one(f.render(), n => n.props.className === 'farm-select-wrap');
    call(one(select, n => n.type === 'select'), 'onChange', { target: { value: 'farm-b' } });
    let review = one(f.render(), n => n.type === PestAlertReview);
    assert.equal(review.props.farmId, 'farm-b'); assert.equal(review.props.mutationMemberId, '');
    f.pending.at(-1)!.resolve(new Response('', { status: 503 })); await flush();
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.mutationMemberId, '', 'failed refresh cannot validate new actor');
    f.refresh(); f.pending.at(-1)!.resolve(Response.json(f.snapshot('farm-b'))); await flush();
    review = one(f.render(), n => n.type === PestAlertReview);
    assert.equal(review.props.mutationMemberId, 'farm-b-member');
  });
});

test('same-farm account and permission snapshots replace the actor; older responses cannot restore it', async () => {
  await fixture(async f => {
    f.refresh(); const old = f.pending.at(-1)!;
    f.refresh(); const next = f.snapshot(); (next.account as Props).memberId = 'SYNTHETIC_NEW_MEMBER';
    f.pending.at(-1)!.resolve(Response.json(next)); await flush();
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.mutationMemberId, 'SYNTHETIC_NEW_MEMBER');
    old.resolve(Response.json(f.snapshot())); await flush();
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.mutationMemberId, 'SYNTHETIC_NEW_MEMBER');
    f.refresh(); const denied = f.snapshot(); (denied.account as Props).permissions = { reviewAlerts: false };
    f.pending.at(-1)!.resolve(Response.json(denied)); await flush();
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.mutationMemberId, '');
  });
});

test('null, missing, malformed, whitespace and unauthenticated actor snapshots never infer a member ID', async () => {
  for (const member of [null, undefined, 42, '', '   ']) await fixture(async f => {
    f.refresh(); const next = f.snapshot(); (next.account as Props).memberId = member;
    f.pending.at(-1)!.resolve(Response.json(next)); await flush();
    assert.equal(one(f.render(), n => n.type === PestAlertReview).props.mutationMemberId, '');
  });
  await fixture(async f => {
    f.refresh(); const next = f.snapshot(); (next.account as Props).authenticated = false;
    f.pending.at(-1)!.resolve(Response.json(next)); await flush();
    assert.equal(nodes(f.render()).some(n => n.type === PestAlertReview), false);
  });
});

test('403 suppresses the delivered actor but transient errors retain the same-farm stale actor', async () => {
  for (const outcome of ['403', '503', 'network']) await fixture(async f => {
    f.refresh(); const request = f.pending.at(-1)!;
    if (outcome === 'network') request.reject(TypeError('SYNTHETIC_OFFLINE'));
    else request.resolve(new Response('', { status: Number(outcome) }));
    await flush(); const review = one(f.render(), n => n.type === PestAlertReview);
    assert.equal(review.props.mutationMemberId, outcome === '403' ? '' : 'farm-a-member');
    assert.equal(review.props.readBlocked, outcome === '403');
  });
});

for (const kind of ['CHECK', 'ACTION', 'CORRECTION', 'RESOLVE'] as const) {
  for (const outcome of ['success', 'error']) for (const timing of ['before-current', 'during-current']) {
  test(`ordinary ${kind} ${outcome}/${timing} completion preserves the current member context`, async () => {
      await fixture(async f => {
        const parent = active, q = harness(); let member = 'member-a', changed = 0;
        const row = { id: 'loc', farm_id: 'farm-a', location_key: 'H:B:Z', display_location: 'SYNTHETIC_LOCATION',
          house_code: 'H', bed_code: 'B', zone_code: 'Z', current_state: 'FIELD_CHECK_REQUIRED', active_case_id: 'case',
          primary_issue_code: null, issue_family: 'PEST', case_status: 'OPEN', observation_count: 1,
          latest_humidity: null, latest_leaf_temp: null, latest_reference_temp: null, latest_ambient_temp: null,
          latest_risk_signal: null, last_alert_reason: null, last_alert_at: null, last_observed_at: null,
          last_field_check_at: null, last_action_at: null };
        const render = () => { active = q; q.reset(); const tree = ScoutingQueue({ farmId: 'farm-a', mutationMemberId: member,
          canReview: true, language: 'ko', onChanged: () => { changed++; } }); q.commit(); return tree; };
        const pick = (code: string) => {
          const picker = one(render(), n => n.type === ScoutingFindingPicker);
          call(picker, 'onSelect', code);
        };
        const finishRead = async () => {
          const request = f.pending.at(-1)!; assert.equal(request.method, 'GET');
          assert.ok(request.url.startsWith('/api/scouting-locations'));
          request.resolve(Response.json({ rows: [row] })); await flush(); render();
        };
        try {
          render(); await flush(); await finishRead();
          call(one(render(), n => typeof n.props.className === 'string' && n.props.className.startsWith('scouting-location-row')));
          if (kind === 'CORRECTION') {
            pick('NO_VISIBLE_EVIDENCE'); await flush();
            f.pending.at(-1)!.resolve(Response.json({ fieldCheckId: 'seed-check', message: 'SEED_SAVED' }));
            await flush(); await finishRead(); changed = 0;
          }
          const submit = () => {
            if (kind === 'CHECK') pick('NO_VISIBLE_EVIDENCE');
            else if (kind === 'ACTION') call(one(render(), n => n.type === 'button' && n.props.children === '방제'));
            else if (kind === 'RESOLVE') call(one(render(), n => n.type === 'button' && n.props.children === '추가 이상 없음'));
            else {
              const panel = one(render(), n => n.props.className === 'scouting-correction-panel');
              call(one(panel, n => n.type === 'button' && n.props.children === '특별한 이상 못 찾음'));
            }
          };
          submit();
          await flush(); const old = f.pending.at(-1)!; assert.equal(old.method, 'POST');
          member = 'member-b'; render(); await flush();
          member = 'member-a'; render();
          member = 'member-b'; render(); await flush(); // returning to an old actor cannot revive an abandoned lock
          await finishRead(); // the new member's fresh list must finish before its controls are exercised
          let current: Pending | undefined;
          const startCurrent = async () => {
            assert.equal(one(render(), n => n.type === ScoutingFindingPicker).props.disabled, false, 'new member must not inherit an orphaned busy lock');
            submit(); await flush(); current = f.pending.at(-1)!;
            assert.equal(current.method, 'POST'); assert.notEqual(current, old);
            assert.equal(one(render(), n => n.type === ScoutingFindingPicker).props.disabled, true);
          };
          if (timing === 'during-current') await startCurrent();
          const calls = f.pending.length;
          old.resolve(outcome === 'success'
            ? Response.json({ fieldCheckId: 'OLD_PRIVATE_CHECK', message: 'OLD_PRIVATE_SAVED', state: 'RESOLVED' })
            : Response.json({ error: 'OLD_PRIVATE_ERROR' }, { status: 503 }));
          await flush(); const tree = render();
          assert.equal(JSON.stringify(tree).includes('OLD_PRIVATE'), false, 'old response cannot set feedback or correction target');
          assert.equal(f.pending.length, calls, 'old completion cannot refresh its list'); assert.equal(changed, 0);
          assert.ok(nodes(tree).some(n => n.type === ScoutingFindingPicker), 'old resolve cannot close current details');
          if (kind === 'CORRECTION') assert.ok(q.states.some(s => s.value && typeof s.value === 'object' && 'fieldCheckId' in s.value && s.value.fieldCheckId === 'seed-check'), 'old correction cannot clear the current target');
          if (timing === 'during-current') assert.equal(one(tree, n => n.type === ScoutingFindingPicker).props.disabled, true, 'old finally cannot unlock the current request');
          else await startCurrent();
          current!.resolve(Response.json({ message: 'NEW_CURRENT_SAVED', ...(kind === 'CHECK' ? { fieldCheckId: 'NEW_CURRENT_CHECK' }
            : kind === 'CORRECTION' ? { correctionId: 'new-correction', correctionKind: 'REPLACE' }
              : kind === 'RESOLVE' ? { caseId: 'case', state: 'RESOLVED' } : { actionCode: 'TREATMENT_APPLIED' }) }));
          await flush(); await finishRead();
          const fresh = render(); assert.ok(JSON.stringify(fresh).includes('NEW_CURRENT_SAVED')); assert.equal(changed, 1);
          if (kind === 'CHECK') assert.ok(q.states.some(s => s.value && typeof s.value === 'object' && 'fieldCheckId' in s.value && s.value.fieldCheckId === 'NEW_CURRENT_CHECK'));
          if (kind === 'CORRECTION') assert.equal(q.states.some(s => s.value && typeof s.value === 'object' && 'fieldCheckId' in s.value), false);
          if (kind === 'RESOLVE') assert.equal(nodes(fresh).some(n => n.type === ScoutingFindingPicker), false, 'current resolve still closes its details');
          else assert.equal(one(fresh, n => n.type === ScoutingFindingPicker).props.disabled, false);
          assert.equal(q.refs.some(ref => ref.current instanceof ScoutingPendingIntent), false, 'keyed default stays off, no intent/key created');
        } finally { q.cleanup(); active = parent; }
      }, 'alerts', kind === 'CORRECTION' ? 3 : 2);
  });
  }
}

for (const kind of ['CHECK', 'ACTION', 'CORRECTION', 'RESOLVE'] as const) for (const outcome of ['success', 'error']) {
  test(`refresh tail ${kind}/${outcome} cannot replace a new member's completed list`, async () => {
    await fixture(async f => {
      const parent = active, q = harness(); let member = 'member-a', changed = 0;
      const row = { id: 'loc', farm_id: 'farm-a', location_key: 'H:B:Z', display_location: 'CURRENT_LOCATION',
        house_code: 'H', bed_code: 'B', zone_code: 'Z', current_state: 'FIELD_CHECK_REQUIRED', active_case_id: 'case',
        primary_issue_code: null, issue_family: 'PEST', case_status: 'OPEN', observation_count: 1,
        latest_humidity: null, latest_leaf_temp: null, latest_reference_temp: null, latest_ambient_temp: null,
        latest_risk_signal: null, last_alert_reason: null, last_alert_at: null, last_observed_at: null,
        last_field_check_at: null, last_action_at: null };
      const render = () => { active = q; q.reset(); const tree = ScoutingQueue({ farmId: 'farm-a', mutationMemberId: member,
        canReview: true, language: 'ko', onChanged: () => { changed++; } }); q.commit(); return tree; };
      const pick = () => call(one(render(), n => n.type === ScoutingFindingPicker), 'onSelect', 'NO_VISIBLE_EVIDENCE');
      const finishRead = async () => { const r = f.pending.at(-1)!; assert.equal(r.method, 'GET'); r.resolve(Response.json({ rows: [row] })); await flush(); render(); };
      try {
        render(); await flush(); await finishRead();
        call(one(render(), n => typeof n.props.className === 'string' && n.props.className.startsWith('scouting-location-row')));
        if (kind === 'CORRECTION') {
          pick(); await flush(); f.pending.at(-1)!.resolve(Response.json({ fieldCheckId: 'seed-check' }));
          await flush(); await finishRead(); changed = 0;
        }
        if (kind === 'CHECK') pick();
        else if (kind === 'ACTION') call(one(render(), n => n.type === 'button' && n.props.children === '방제'));
        else if (kind === 'RESOLVE') call(one(render(), n => n.type === 'button' && n.props.children === '추가 이상 없음'));
        else call(one(one(render(), n => n.props.className === 'scouting-correction-panel'), n => n.type === 'button' && n.props.children === '특별한 이상 못 찾음'));
        await flush(); const post = f.pending.at(-1)!; assert.equal(post.method, 'POST');
        post.resolve(Response.json({ fieldCheckId: 'check', message: 'SAVED_BEFORE_SWITCH' })); await flush();
        const oldRead = f.pending.at(-1)!; assert.equal(oldRead.method, 'GET');
        member = 'member-b'; render(); await flush();
        const newRead = f.pending.at(-1)!;
        assert.notEqual(newRead, oldRead, 'new member must own a fresh read');
        await finishRead(); const before = JSON.stringify(q.states), calls = f.pending.length;
        oldRead.resolve(outcome === 'success' ? Response.json({ rows: [{ ...row, id: 'OLD_REFRESH', display_location: 'OLD_REFRESH' }] })
          : Response.json({ error: 'OLD_REFRESH_ERROR' }, { status: 503 }));
        await flush(); const tree = render();
        assert.equal(JSON.stringify(q.states), before, 'late old list completion cannot mutate current state');
        assert.equal(JSON.stringify(tree).includes('OLD_REFRESH'), false); assert.equal(changed, 0);
        assert.equal(f.pending.length, calls); assert.ok(JSON.stringify(tree).includes('CURRENT_LOCATION'));
      } finally { q.cleanup(); active = parent; }
    }, 'alerts', kind === 'CORRECTION' ? 2 : 1);
  });
}
