import assert from 'node:assert/strict';
import { test } from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { pestTargets } from '../app/features/pests/domain/catalog';
import { PestOverviewCard, activePestSummary } from '../app/features/pests/presentation/PestOverviewCard';

const targets = pestTargets.map((target) => ({ code: target.code, openCount: target.code === 'MITE' ? 1 : target.code === 'POWDERY_MILDEW' ? 2 : 0 }));

test('operating overview exposes every pest and disease rather than only the active mite target', () => {
  const html = renderToStaticMarkup(<PestOverviewCard targets={targets} total={3} language="ko" state="ready" onSelect={() => {}} />);
  for (const target of pestTargets) assert.ok(html.includes(target.labels.ko), `${target.code} must remain visible`);
  assert.ok(html.includes('해충') && html.includes('병해·곰팡이'));
  assert.ok(html.includes('전체 기록 보기'));
  assert.ok(!html.includes('<details'), 'types must be visible without opening a collapsed list');
  assert.ok(!html.includes('응애 확인 목록') && !html.includes('응애 예찰 · 사용 중'));
  assert.equal(activePestSummary(targets, 'ko'), '응애 · 흰가루병');
  assert.equal(activePestSummary([{ code: 'APHID', openCount: 2 }], 'ko'), '진딧물');
});

test('missing farm data never appears as a clean field result', () => {
  const html = renderToStaticMarkup(<PestOverviewCard targets={targets} total={0} language="ko" state="unlinked" onSelect={() => {}} />);
  assert.ok(html.includes('농장 연결 후'));
  assert.ok(html.includes('—'));
  assert.ok(!html.includes('정상'));
  assert.equal((html.match(/disabled=""/g) ?? []).length, pestTargets.length + 1);
});

test('operating overview labels follow the selected worker language', () => {
  for (const language of ['vi', 'th', 'zh-CN'] as const) {
    const html = renderToStaticMarkup(<PestOverviewCard targets={targets} total={3} language={language} state="ready" onSelect={() => {}} />);
    for (const target of pestTargets) assert.ok(html.includes(target.labels[language]));
  }
});
