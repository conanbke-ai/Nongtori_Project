// 합성 함수만 사용합니다. 실제 ps/파일 쓰기/브라우저를 실행하는 검사가 아닙니다.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { finishBrowserReceipt, prepareLinuxChildObservation } from './dashboard-stream403-runner.mjs';

function fixture(status = 'PASS') {
  const result = { status, resources: [], cleanupErrors: [] };
  const written = [];
  const options = { preservationCheck: () => true, observeChildren: () => '', writeReceipt: r => written.push(structuredClone(r)), now: () => 'SYNTHETIC_TIME' };
  return { result, options, written };
}

test('실행기 정상 정리·사후 관측·영수증 성공만 PASS로 남긴다', () => {
  const f = fixture(), final = finishBrowserReceipt(f.result, f.options);
  assert.deepEqual(final, { ok: true, receiptWritten: true });
  assert.equal(f.written.length, 1); assert.equal(f.written[0].status, 'PASS');
  assert.equal(f.written[0].processObservation.status, 'observed');
  assert.deepEqual(f.written[0].cleanupErrors, []);
});

test('최초 테스트 실패와 정리 오류는 사후 ps 실패로 덮이지 않는다', () => {
  const f = fixture('FAIL'); f.result.failure = 'SYNTHETIC_FIRST_FAILURE';
  f.result.cleanupErrors.push({ name: 'browser', error: 'SYNTHETIC_CLEANUP_FAILURE' });
  f.options.observeChildren = () => { throw Error('SYNTHETIC_PS_FAILURE'); };
  assert.deepEqual(finishBrowserReceipt(f.result, f.options), { ok: false, receiptWritten: true });
  assert.equal(f.written.length, 1); assert.equal(f.written[0].status, 'FAIL');
  assert.equal(f.written[0].failure, 'SYNTHETIC_FIRST_FAILURE');
  assert.deepEqual(f.written[0].cleanupErrors, f.result.cleanupErrors);
  assert.match(f.written[0].processObservation.error, /SYNTHETIC_PS_FAILURE/);
});

test('사후 관측만 실패해도 영수증을 쓰고 자원 종료 PASS를 주지 않는다', () => {
  const f = fixture(); f.options.observeChildren = () => { throw Error('SYNTHETIC_PS_FAILURE'); };
  assert.equal(finishBrowserReceipt(f.result, f.options).ok, false);
  assert.equal(f.written.length, 1); assert.equal(f.written[0].status, 'BLOCKED');
  assert.equal(f.written[0].summary.pass, 0);
});

test('영수증 쓰기 실패는 최초 원인을 유지하고 false success 없이 한 번 중단한다', () => {
  for (const status of ['PASS', 'FAIL']) {
    const f = fixture(status); let attempts = 0;
    if (status === 'FAIL') f.result.failure = 'SYNTHETIC_FIRST_FAILURE';
    f.options.writeReceipt = () => { attempts++; throw Error('SYNTHETIC_WRITE_FAILURE'); };
    assert.deepEqual(finishBrowserReceipt(f.result, f.options), { ok: false, receiptWritten: false });
    assert.equal(attempts, 1); assert.equal(f.result.summary.pass, 0);
    assert.match(f.result.receiptWriteError, /SYNTHETIC_WRITE_FAILURE/);
    if (status === 'FAIL') assert.equal(f.result.failure, 'SYNTHETIC_FIRST_FAILURE');
  }
});

test('Linux 필수 ps 인자를 사전 확인하고 다른 OS·준비 실패에서 대체 조회하지 않는다', () => {
  const calls = [];
  const ready = prepareLinuxChildObservation({ platform: 'linux', pid: 123, execFile: (...args) => { calls.push(args); return ' SYNTHETIC_CHILD '; } });
  assert.equal(ready.preflight, 'SYNTHETIC_CHILD');
  assert.deepEqual(calls[0], ['ps', ['-o', 'pid=,stat=,comm=', '--ppid', '123'], { encoding: 'utf8', timeout: 4000 }]);
  let attempts = 0;
  assert.throws(() => prepareLinuxChildObservation({ platform: 'win32', pid: 123, execFile: () => { attempts++; } }), /Linux만/);
  assert.equal(attempts, 0);
  assert.throws(() => prepareLinuxChildObservation({ platform: 'linux', pid: 123, execFile: () => { attempts++; throw Error('SYNTHETIC_PS_UNAVAILABLE'); } }), /SYNTHETIC_PS_UNAVAILABLE/);
  assert.equal(attempts, 1);
});

test('보존·시각 관측 예외도 별도 기록하고 영수증 시도를 건너뛰지 않는다', () => {
  const f = fixture(); f.options.preservationCheck = () => { throw Error('SYNTHETIC_PRESERVATION_FAILURE'); };
  f.options.now = () => { throw Error('SYNTHETIC_CLOCK_FAILURE'); };
  assert.equal(finishBrowserReceipt(f.result, f.options).ok, false);
  assert.equal(f.written.length, 1); assert.equal(f.written[0].status, 'BLOCKED');
  assert.match(f.written[0].finalizationErrors[0].error, /SYNTHETIC_PRESERVATION_FAILURE/);
  assert.match(f.written[0].finalizationErrors[1].error, /SYNTHETIC_CLOCK_FAILURE/);
});
