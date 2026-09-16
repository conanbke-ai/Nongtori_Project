import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { ScoutingQueue } from '../app/features/pests/presentation/ScoutingQueue';

test('scouting queue does not turn missing visible evidence into a mite-negative claim', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview language="ko" />);
  assert.ok(html.includes('오늘 확인할 곳'));
  assert.ok(html.includes('지금 바로 확인할 구역이 없습니다.'));
  assert.ok(html.includes('“특별한 이상을 못 찾음”은 응애가 없다는 확정 판정이 아닙니다.'));
  assert.ok(!html.includes('응애 아님'));
});

test('scouting queue remains read-only for workers without review permission', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview={false} language="vi" />);
  assert.ok(html.includes('구역 상태 기반 예찰'));
  assert.ok(!html.includes('현장 점검 결과'));
  assert.ok(!html.includes('조치 기록'));
});
