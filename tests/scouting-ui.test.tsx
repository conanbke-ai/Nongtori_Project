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

test('scouting action labels are concise operational nouns', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview language="ko" />);
  assert.ok(html.includes('방제'));
  assert.ok(html.includes('피해잎 제거'));
  assert.ok(html.includes('천적 처리'));
  assert.ok(html.includes('추적 관찰'));
  assert.ok(!html.includes('방제했어요'));
  assert.ok(!html.includes('제거했어요'));
  assert.ok(!html.includes('지켜볼게요'));
});

test('scouting queue remains read-only and localized for workers without review permission', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview={false} language="vi" />);
  assert.ok(html.includes('Theo dõi theo trạng thái khu vực'));
  assert.ok(html.includes('Khu vực cần kiểm tra hôm nay'));
  assert.ok(!html.includes('현장 점검 결과'));
  assert.ok(!html.includes('조치 기록'));
});
