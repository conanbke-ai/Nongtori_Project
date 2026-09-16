import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
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
  const source = readFileSync('app/features/pests/presentation/ScoutingQueue.tsx', 'utf8');
  for (const label of ["ko: '방제'", "ko: '피해잎 제거'", "ko: '천적 처리'", "ko: '추적 관찰'", "ko: '기타 조치'"]) {
    assert.ok(source.includes(label), `${label} must remain in the action catalog`);
  }
  assert.ok(!source.includes("ko: '방제했어요'"));
  assert.ok(!source.includes("ko: '피해잎을 제거했어요'"));
  assert.ok(!source.includes("ko: '조금 더 지켜볼게요'"));
});

test('scouting queue remains read-only and localized for workers without review permission', () => {
  const html = renderToStaticMarkup(<ScoutingQueue farmId="" canReview={false} language="vi" />);
  assert.ok(html.includes('Theo dõi theo trạng thái khu vực'));
  assert.ok(html.includes('Khu vực cần kiểm tra hôm nay'));
  assert.ok(!html.includes('현장 점검 결과'));
  assert.ok(!html.includes('조치 기록'));
});
