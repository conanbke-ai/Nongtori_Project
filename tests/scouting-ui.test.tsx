import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { renderToStaticMarkup } from 'react-dom/server';
import { ScoutingQueue } from '../app/features/pests/presentation/ScoutingQueue';

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
