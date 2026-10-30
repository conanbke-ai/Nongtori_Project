import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
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
