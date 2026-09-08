'use client';

import { FormEvent, useState } from 'react';

type SubmitState = { kind: 'idle' | 'sending' | 'success' | 'error'; message: string };

export function ObservationForm() {
  const [state, setState] = useState<SubmitState>({ kind: 'idle', message: '' });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: 'sending', message: '원본 파일을 안전하게 저장하는 중입니다…' });
    const form = event.currentTarget;
    try {
      const response = await fetch('/api/observations', { method: 'POST', body: new FormData(form) });
      const result = (await response.json()) as { observationId?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? '관측 저장에 실패했습니다.');
      form.reset();
      setState({ kind: 'success', message: `관측 ${result.observationId?.slice(0, 8)} 저장 완료 · 아직 확진 전입니다.` });
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : '관측 저장에 실패했습니다.' });
    }
  }

  return (
    <form className="observation-form" onSubmit={submit}>
      <input name="cultivar" type="hidden" value="SEOLHYANG" />
      <input name="farmId" type="hidden" value="FARM-01" />
      <label className="select-field">촬영 방식
        <select defaultValue="PAIRED_STILL" name="captureMethod" required>
          <option value="PAIRED_STILL">RGB·열화상 별도 정지사진</option>
          <option value="EXTRACTED_VIDEO_FRAMES">영상에서 추출한 프레임</option>
          <option value="DUAL_SENSOR_SIMULTANEOUS">동시 저장 카메라</option>
        </select>
      </label>
      <div className="field-grid">
        <label>하우스<input name="houseId" defaultValue="1동" required /></label>
        <label>베드<input name="bedId" defaultValue="B" required /></label>
        <label>구역<input name="zoneId" defaultValue="02" required /></label>
        <label>잎 ID<input name="leafId" placeholder="예: L-024" /></label>
        <label>페어링 ID<input name="pairingId" placeholder="예: B02-20260827-001" required /></label>
        <label>원본 영상 ID<input name="sourceVideoId" placeholder="프레임 자료일 때 입력" /></label>
        <label>RGB 프레임 번호<input min="0" name="rgbFrameIndex" placeholder="선택" type="number" /></label>
        <label>열화상 프레임 번호<input min="0" name="thermalFrameIndex" placeholder="선택" type="number" /></label>
      </div>
      <label className="file-field">RGB 사진 또는 추출 프레임<input accept="image/jpeg,image/png,image/webp,image/tiff" name="rgb" required type="file" /></label>
      <label className="file-field">Radiometric 열화상 원본 또는 추출 프레임<input name="thermal" required type="file" /></label>
      <label className="file-field optional">잎 뒷면 매크로 <span>선택</span><input accept="image/*" name="macro" type="file" /></label>
      <button className="upload-area" disabled={state.kind === 'sending'} type="submit">
        <span aria-hidden="true">＋</span>
        <strong>{state.kind === 'sending' ? '저장 중…' : '관측 묶음 저장'}</strong>
        <small>원본은 변환하지 않고 보존합니다</small>
      </button>
      {state.kind !== 'idle' && <p className={`form-status ${state.kind}`} role="status">{state.message}</p>}
    </form>
  );
}
