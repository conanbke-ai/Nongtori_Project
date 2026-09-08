'use client';

import { FormEvent, useState } from 'react';

type SubmitState = { kind: 'idle' | 'sending' | 'success' | 'error'; message: string };

export function FruitAssessmentForm({
  cultivarCode = 'SEOLHYANG',
  cultivarName = '설향',
}: {
  cultivarCode?: string;
  cultivarName?: string;
}) {
  const [state, setState] = useState<SubmitState>({ kind: 'idle', message: '' });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({ kind: 'sending', message: `${cultivarName} 과실 사진을 접수하는 중입니다…` });
    const form = event.currentTarget;

    try {
      const response = await fetch('/api/fruit-assessments', {
        method: 'POST',
        body: new FormData(form),
      });
      const result = (await response.json()) as { assessmentId?: string; message?: string; error?: string };
      if (!response.ok) throw new Error(result.error ?? '과실 사진 저장에 실패했습니다.');
      form.reset();
      setState({
        kind: 'success',
        message: result.message ?? '사진을 접수했습니다.',
      });
    } catch (error) {
      setState({
        kind: 'error',
        message: error instanceof Error ? error.message : '과실 사진 저장에 실패했습니다.',
      });
    }
  }

  return (
    <form className="fruit-form" onSubmit={submit}>
      <input name="cultivar" type="hidden" value={cultivarCode} />
      <label className="file-field">
        {cultivarName} 과실 사진
        <input accept="image/jpeg,image/png,image/webp" capture="environment" name="image" required type="file" />
      </label>
      <button className="fruit-submit" disabled={state.kind === 'sending'} type="submit">
        {state.kind === 'sending' ? '접수 중…' : '사진 접수하기'}
      </button>
      <p className="form-note">현재는 학습용 원본 접수 단계이며, 검증된 모델 연결 전에는 판정 결과를 표시하지 않습니다.</p>
      {state.kind !== 'idle' && (
        <p className={`form-status ${state.kind}`} role="status">{state.message}</p>
      )}
    </form>
  );
}
