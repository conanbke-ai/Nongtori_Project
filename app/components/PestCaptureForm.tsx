'use client';

import { FormEvent, useLayoutEffect, useRef, useState } from 'react';
import { pestTargets, pestLabel } from '@/app/features/pests/domain/catalog';
import { pestText } from '@/app/features/pests/presentation/text';
import { translate, type Language } from '@/app/lib/i18n';
import { pestCaptureGuidance, submitPestCapture, type PestCaptureResult } from '@/app/features/pests/presentation/pest-capture-submission';

export function PestCaptureForm({ farmId, itemId, language, onUploaded, defaultPestCode = 'OTHER' }: { defaultPestCode?: string; farmId: string; itemId: string; language: Language; onUploaded: () => void }) {
  const scope = JSON.stringify([farmId, itemId]);
  const [state, setState] = useState<({ kind: 'idle' } | { kind: 'sending' } | PestCaptureResult) & { scope: string }>({ kind: 'idle', scope });
  const contextId = useRef(0);
  const busyContext = useRef<number | null>(null);
  const uncertainContext = useRef<number | null>(null);
  useLayoutEffect(() => {
    contextId.current += 1;
    return () => { contextId.current += 1; };
  }, [farmId, itemId]);
  const current = state.scope === scope ? state : { kind: 'idle' as const, scope };
  const guidance = current.kind === 'idle' || current.kind === 'sending' ? null : pestCaptureGuidance(current, language);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const requestContext = contextId.current;
    if (!farmId || busyContext.current === requestContext || uncertainContext.current === requestContext || current.kind === 'uncertain') return;
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set('farmId', farmId);
    body.set('itemId', itemId);
    busyContext.current = requestContext;
    setState({ kind: 'sending', scope });
    try {
      const result = await submitPestCapture(body, { onReceived: onUploaded, isCurrent: () => contextId.current === requestContext });
      if (contextId.current !== requestContext) return;
      if (result.kind === 'uncertain') uncertainContext.current = requestContext;
      if (result.kind === 'received') {
        try { form.reset(); } catch { result.refreshFailed = true; }
      }
      setState({ ...result, scope });
    } finally { if (busyContext.current === requestContext) busyContext.current = null; }
  }

  return (
    <form className="mite-capture-form" onSubmit={submit}>
      <label><span>{pestText(language, 'target')}</span><select name="pestCode" defaultValue={defaultPestCode} disabled={current.kind === 'sending'} required>{pestTargets.map((target) => <option value={target.code} key={target.code}>{pestLabel(target.code, language)}</option>)}</select></label>
      <p>{pestText(language, 'unknownHelp')} {pestText(language, 'scope')}</p>
      <label><span>{translate(language, 'upload.rgb')} <b>{translate(language, 'upload.required')}</b></span><input accept="image/*" capture="environment" disabled={current.kind === 'sending'} name="rgbImage" required type="file" /></label>
      <label><span>{translate(language, 'upload.thermal')} <small>{translate(language, 'common.optional')}</small></span><input accept="image/*" disabled={current.kind === 'sending'} name="thermalImage" type="file" /></label>
      <p>{translate(language, 'upload.photoHelp')}</p>
      <button disabled={!farmId || current.kind === 'sending' || current.kind === 'uncertain'} type="submit">{current.kind === 'sending' ? translate(language, 'common.loading') : translate(language, 'upload.submit')}</button>
      {current.kind === 'sending' && <div className="upload-status sending" role="status">{translate(language, 'upload.photoSending')}</div>}
      {guidance && <div className={`upload-status ${current.kind === 'received' ? 'success' : 'error'}`} role={current.kind === 'received' ? 'status' : 'alert'}>
        <strong>{guidance.title}</strong><p>{guidance.reason}</p><p>{guidance.action}</p>
        {current.kind === 'received' && <p>{pestText(language, 'target')}: {pestLabel(current.pestCode, language)}</p>}
        {guidance.refreshWarning && <p>{guidance.refreshWarning}</p>}
      </div>}
    </form>
  );
}
