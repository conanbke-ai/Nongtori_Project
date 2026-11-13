import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { ScoutingHistory, ScoutingHistoryPanel } from '../app/features/pests/presentation/ScoutingHistory';
import { historyScope, projectScoutingHistory, ScoutingHistoryReader, type HistoryLoadState } from '../app/features/pests/presentation/scouting-history-reader';
import {
  ScoutingQueue,
  scoutingRowsForFarm,
  scoutingQueueViewState,
} from '../app/features/pests/presentation/ScoutingQueue';

test('scouting queue distinguishes loading, failure, empty, current, and stale states', () => {
  const state = (overrides: Partial<Parameters<typeof scoutingQueueViewState>[0]> = {}) => scoutingQueueViewState({
    farmId: 'farm-a', loadedFarmId: '', loading: false, loadError: '', rowCount: 0, ...overrides,
  });

  assert.equal(state(), 'LOADING', 'a farm must not look empty before its first response');
  assert.equal(state({ loadError: '503' }), 'ERROR', 'an initial failure must not look like a successful empty response');
  assert.equal(state({ loadedFarmId: 'farm-a' }), 'EMPTY', 'only a successful zero-row response is empty');
  assert.equal(state({ loadedFarmId: 'farm-a', rowCount: 1 }), 'READY');
  assert.equal(state({ loadedFarmId: 'farm-a', rowCount: 1, loadError: '503' }), 'STALE');
  assert.equal(
    state({ farmId: 'farm-b', loadedFarmId: 'farm-a', rowCount: 0 }),
    'LOADING',
    'a previous farm snapshot must not become the new farm empty state',
  );
  assert.equal(
    state({ loadedFarmId: 'farm-a', rowCount: 1, loadError: '' }),
    'READY',
    'a successful retry clears the failure state',
  );
});

test('scouting queue never projects another farm snapshot and ignores superseded loads', () => {
  const farmARows = [{ id: 'location-a' }];
  assert.deepEqual(scoutingRowsForFarm(farmARows, 'farm-a', 'farm-a'), farmARows);
  assert.deepEqual(scoutingRowsForFarm(farmARows, 'farm-a', 'farm-b'), []);

  const source = readFileSync('app/features/pests/presentation/ScoutingQueue.tsx', 'utf8');
  assert.match(source, /const requestId = \+\+loadRequestId\.current/);
  assert.match(source, /if \(requestId !== loadRequestId\.current\) return/);
  assert.match(source, /if \(requestId === loadRequestId\.current\) setLoading\(false\)/);
});

test('scouting queue starts with loading instead of a false all-clear for a connected farm', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="farm-a" canReview language="ko" />);
  assert.ok(html.includes('예찰 구역을 불러오는 중입니다.'));
  assert.ok(!html.includes('지금 바로 확인할 구역이 없습니다.'));
});

test('scouting queue treats no visible abnormality as observation, not a confirmed negative', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview language="ko" />);
  assert.ok(html.includes('오늘 확인할 구역'));
  assert.ok(html.includes('지금 바로 확인할 구역이 없습니다.'));
  assert.ok(!html.includes('응애 아님'));
});

test('scouting workflow status is separated from pest identity', () => {
  const source = readFileSync('app/features/pests/presentation/ScoutingQueue.tsx', 'utf8');
  assert.ok(source.includes("CONFIRMED: { ko: '현장 확인 완료'"));
  assert.ok(source.includes("SPIDER_MITE: { ko: '응애'"));
  assert.ok(!source.includes("CONFIRMED: { ko: '응애 확인'"));
});

test('scouting list stays summary-first and moves field inputs into detail', () => {
  const source = readFileSync('app/features/pests/presentation/ScoutingQueue.tsx', 'utf8');
  assert.ok(source.includes('scouting-location-row'));
  assert.ok(source.includes('scouting-detail-panel'));
  assert.ok(source.includes("fieldCheck: '현장 확인 결과 기록'"));
  assert.ok(source.includes('row.display_location?.trim() || row.location_key?.trim()'));
  assert.ok(source.includes('습도 ${Math.round(row.latest_humidity)}%'));
  assert.ok(source.includes('잎 온도 ${delta >= 0 ?'));
});

test('scouting display projection normalizes legacy colon location keys for users', () => {
  const source = readFileSync('app/api/scouting-locations/route.ts', 'utf8');
  assert.ok(source.includes("REPLACE(TRIM(s.location_key), ':', '-')"));
});

test('scouting action labels remain concise operational nouns', () => {
  const source = readFileSync('app/features/pests/presentation/ScoutingQueue.tsx', 'utf8');
  for (const label of ["ko: '방제'", "ko: '피해잎 제거'", "ko: '천적 처리'", "ko: '추적 관찰'", "ko: '기타 조치'"]) {
    assert.ok(source.includes(label), `${label} must remain in the action catalog`);
  }
});

test('scouting queue remains read-only and localized for workers without review permission', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview={false} language="vi" />);
  assert.ok(html.includes('Theo dõi sâu bệnh'));
  assert.ok(html.includes('Khu vực cần kiểm tra hôm nay'));
  assert.ok(!html.includes('현장 확인 결과 기록'));
  assert.ok(!html.includes('조치 기록'));
});

// Synthetic existing API response; not captured farm data or inferred diagnosis.
function historyFixture(farm='farm-a',location='loc-a') {
  const row=<T extends object>(id:string,extra:T)=>({id,farm_id:farm,location_state_id:location,...extra});
  return {location:{id:location,farm_id:farm},
    observations:[row('obs',{observed_at:'2026-09-25T08:00:00Z',source_type:'THERMAL',thermal_features_json:'PRIVATE_JSON'})],
    fieldChecks:[row('check',{checked_at:'2026-09-25T08:10:00Z',primary_evidence_code:'NO_VISIBLE_EVIDENCE',note:'PRIVATE_NOTE',checker_member_id:'PRIVATE_ACTOR'})],
    corrections:[row('fix',{created_at:'2026-09-25T08:20:00Z',correction_kind:'VOID',field_check_id:'check',replacement_evidence_code:null})],
    actions:[row('action',{action_at:'2026-09-25T08:30:00Z',action_code:'OBSERVE_ONLY'})],
    alerts:[row('alert',{created_at:'2026-09-25T08:01:00Z',alert_decision:'ISSUED'})],
    caseEvents:[row('close',{created_at:'2026-09-25T08:40:00Z',event_type:'RESOLVED'})]};
}

test('history projects six immutable record families without applying VOID or leaking raw notes/identity',()=>{
  const raw=historyFixture(),before=JSON.stringify(raw),entries=projectScoutingHistory(raw,'farm-a','loc-a');
  assert.equal(entries.length,6);assert.deepEqual(entries.map(x=>x.id),['close','action','fix','check','alert','obs']);
  assert.equal(entries.find(x=>x.kind==='fieldChecks')?.code,'NO_VISIBLE_EVIDENCE');
  assert.equal(entries.find(x=>x.kind==='corrections')?.originalCheckId,'check');
  assert.equal(entries.find(x=>x.kind==='corrections')?.code,'VOID');
  assert.equal(JSON.stringify(raw),before);assert.equal(JSON.stringify(entries).includes('PRIVATE_'),false);
  assert.throws(()=>projectScoutingHistory(raw,'farm-b','loc-a'));
  const bad=historyFixture();bad.actions[0].farm_id='farm-b';assert.throws(()=>projectScoutingHistory(bad,'farm-a','loc-a'));
  assert.throws(()=>projectScoutingHistory({...raw,alerts:null},'farm-a','loc-a'));
  assert.throws(()=>projectScoutingHistory({...raw,observations:Array.from({length:51},()=>raw.observations[0])},'farm-a','loc-a'));
});

test('history preserves unknown timestamps as unknown with stable tie order, not manufactured dates',()=>{
  const raw=historyFixture();raw.observations[0].observed_at='bad-time';
  const one=projectScoutingHistory(raw,'farm-a','loc-a'),two=projectScoutingHistory(raw,'farm-a','loc-a');
  assert.equal(one.at(-1)?.at,null);assert.deepEqual(one,two);
  raw.observations[0].observed_at='1';assert.equal(projectScoutingHistory(raw,'farm-a','loc-a').find(x=>x.id==='obs')?.at,null);
  for(const at of ['2026-02-31T08:00:00Z','2026-02-29T08:00:00Z','2026-09-25T24:00:00Z']){
    raw.observations[0].observed_at=at;assert.equal(projectScoutingHistory(raw,'farm-a','loc-a').find(x=>x.id==='obs')?.at,null);
    assert.equal(raw.observations[0].observed_at,at,'source timestamp must not be rewritten');
  }
  raw.observations[0].observed_at='2024-02-29T08:00:00+09:00';
  assert.equal(projectScoutingHistory(raw,'farm-a','loc-a').find(x=>x.id==='obs')?.at,'2024-02-29T08:00:00+09:00');
  assert.notEqual(historyScope('a:b','c'),historyScope('a','b:c'));
});

test('history reader separates first failure/empty/stale and clears retained rows on permission or scope denial',async()=>{
  let response:()=>Promise<Response>=async()=>{throw Error('PRIVATE_TRANSPORT_ERROR');};
  const states:HistoryLoadState[]=[],reader=new ScoutingHistoryReader(async(url,init)=>{
    const u=new URL(String(url),'https://synthetic.test');assert.equal(u.pathname,'/api/scouting-history');
    assert.equal(u.searchParams.get('farmId'),'farm-a');assert.equal(u.searchParams.get('locationStateId'),'loc-a');
    assert.equal(u.searchParams.get('limit'),'50');assert.equal(init?.method,'GET');assert.equal(init.cache,'no-store');return response();
  });
  await reader.load('farm-a','loc-a',s=>states.push(s));assert.equal(states.at(-1)?.status,'error');
  response=async()=>Response.json(historyFixture());await reader.load('farm-a','loc-a',s=>states.push(s));assert.equal(states.at(-1)?.status,'ready');
  response=async()=>Response.json({error:'PRIVATE_DB_STACK'},{status:503});await reader.load('farm-a','loc-a',s=>states.push(s));
  assert.equal(states.at(-1)?.status,'stale');assert.equal(states.at(-1)?.entries.length,6);
  response=async()=>Response.json({error:'PRIVATE_AUTH_STACK'},{status:403});await reader.load('farm-a','loc-a',s=>states.push(s));
  assert.equal(states.at(-1)?.status,'error');assert.deepEqual(states.at(-1)?.entries,[]);
  response=async()=>Response.json({...historyFixture(),observations:[],fieldChecks:[],corrections:[],actions:[],alerts:[],caseEvents:[]});
  await reader.load('farm-a','loc-a',s=>states.push(s));assert.equal(states.at(-1)?.status,'ready');assert.deepEqual(states.at(-1)?.entries,[]);
  response=async()=>Response.json(historyFixture('farm-b','loc-b'));await reader.load('farm-a','loc-a',s=>states.push(s));assert.equal(states.at(-1)?.status,'error');
  assert.equal(JSON.stringify(states).includes('PRIVATE_'),false);
});

test('history GET is explicit, coalesces duplicates and discards invalidated or superseded responses',async()=>{
  const pending:((r:Response)=>void)[]=[],states:HistoryLoadState[]=[];let calls=0;
  const reader=new ScoutingHistoryReader(async()=>{calls++;return new Promise<Response>(resolve=>pending.push(resolve));});
  assert.equal(calls,0);const first=reader.load('farm-a','loc-a',s=>states.push(s));
  await reader.load('farm-a','loc-a',s=>states.push(s));assert.equal(calls,1);
  reader.invalidate();const second=reader.load('farm-b','loc-b',s=>states.push(s));
  pending[1](Response.json(historyFixture('farm-b','loc-b')));await second;
  const snapshot=JSON.stringify(states);pending[0](Response.json(historyFixture()));await first;
  assert.equal(JSON.stringify(states),snapshot);assert.equal(states.at(-1)?.scope,historyScope('farm-b','loc-b'));
  const closing=reader.load('farm-b','loc-b',s=>states.push(s));reader.invalidate();const closed=JSON.stringify(states);
  pending[2](Response.json({error:'PRIVATE_ERROR'},{status:403}));await closing;assert.equal(JSON.stringify(states),closed);
});

test('history UI distinguishes not-loaded/error/empty/stale, links original checks and advertises bounded scope',()=>{
  for(const language of ['ko','vi','th','zh-CN'] as const){
    const initial=renderToStaticMarkup(<ScoutingHistory farmId="farm-a" locationId="loc-a" language={language}/>);
    assert.match(initial,/aria-expanded="false"/);assert.equal(initial.includes('<ol>'),false);
    const entries=projectScoutingHistory(historyFixture(),'farm-a','loc-a');
    const html=renderToStaticMarkup(<ScoutingHistoryPanel language={language} state={{scope:historyScope('farm-a','loc-a'),status:'ready',entries}} onRetry={()=>{}}/>);
    assert.match(html,/scouting-history-check-check/);assert.match(html,/50/);assert.equal(html.includes('PRIVATE_'),false);
    assert.equal(html.includes('NO_VISIBLE_EVIDENCE'),false,'unknown code is not dumped as technical/raw text');
  }
  const view=(status:HistoryLoadState['status'],entries:HistoryLoadState['entries']=[])=>renderToStaticMarkup(<ScoutingHistoryPanel language="ko" state={{scope:'synthetic',status,entries}} onRetry={()=>{}}/>);
  assert.match(view('idle'),/이력을 조회해 주세요/);assert.equal(view('error').includes('저장된 이력이 없습니다'),false);
  assert.match(view('ready'),/병해충이 없다는 뜻은 아닙니다/);assert.match(view('stale',projectScoutingHistory(historyFixture(),'farm-a','loc-a')),/이전 조회 결과/);
  assert.match(view('ready',projectScoutingHistory(historyFixture(),'farm-a','loc-a')),/입력 무효/);
  assert.match(readFileSync('app/features/pests/presentation/ScoutingQueue.tsx','utf8'),/<ScoutingHistory key=\{JSON.stringify\(\[farmId, selected.id\]\)\}/);
});
