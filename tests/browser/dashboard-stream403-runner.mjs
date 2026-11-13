// 브라우저/프로세스를 직접 실행하지 않는 실행기 경계입니다.
// 실제 ps와 파일 쓰기는 호출자가 주입하고, 회귀에서는 메모리 함수로 대체합니다.
export function prepareLinuxChildObservation({ platform, pid, execFile }) {
  if (platform !== 'linux') throw new Error('이 브라우저 QA 실행기는 Linux만 지원합니다. 다른 OS 대체 조회를 수행하지 않습니다.');
  const args = ['-o', 'pid=,stat=,comm=', '--ppid', String(pid)];
  const observe = () => execFile('ps', args, { encoding: 'utf8', timeout: 4000 }).trim();
  // 동일한 필수 도구/인자를 브라우저 생성 전에 검증합니다.
  return { preflight: observe(), observe };
}

export function finishBrowserReceipt(result, { preservationCheck, observeChildren, writeReceipt, now = () => new Date().toISOString() }) {
  result.finalizationErrors = [];
  try {
    result.protectedUnchanged = preservationCheck();
    if (!result.protectedUnchanged) {
      result.finalizationErrors.push({ stage: 'preservation', error: '제품/등록 입력 변경 감지' });
      if (result.status === 'PASS') result.status = 'FAIL';
    }
  } catch (error) {
    result.protectedUnchanged = false;
    result.finalizationErrors.push({ stage: 'preservation', error: String(error) });
  }
  try {
    const children = observeChildren();
    result.processObservation = { status: 'observed', children };
    result.resources.push({ event: 'children-after-close', children });
  } catch (error) {
    result.processObservation = { status: 'failed', error: String(error) };
    result.finalizationErrors.push({ stage: 'process-observation', error: String(error) });
  }
  try {
    result.finishedAt = now();
  } catch (error) {
    result.finalizationErrors.push({ stage: 'clock', error: String(error) });
  }
  // 최초 테스트 failure와 cleanupErrors는 유지하고 후속 오류를 별도 보관합니다.
  if (result.status === 'PASS' && ((result.cleanupErrors?.length ?? 0) > 0 || result.finalizationErrors.length > 0)) result.status = 'BLOCKED';
  const summary = () => ({ total: 1, pass: result.status === 'PASS' ? 1 : 0, fail: result.status === 'FAIL' ? 1 : 0, blocked: result.status === 'BLOCKED' ? 1 : 0 });
  result.summary = summary();
  let receiptWritten = false;
  try {
    // 관측/보존/정리 실패 뒤에도 정확히 한 번 시도합니다. 실패 쓰기를 반복하지 않습니다.
    writeReceipt(result);
    receiptWritten = true;
  } catch (error) {
    result.receiptWriteError = String(error);
    if (result.status === 'PASS') result.status = 'BLOCKED';
    result.summary = summary();
  }
  return { ok: result.status === 'PASS' && receiptWritten, receiptWritten };
}
