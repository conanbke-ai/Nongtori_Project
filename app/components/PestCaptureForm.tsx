'use client';

import { FormEvent, useState } from 'react';
import { pestTargets, pestLabel } from '@/app/features/pests/domain/catalog';
import { pestText } from '@/app/features/pests/presentation/text';
import { translate, type Language } from '@/app/lib/i18n';

export function PestCaptureForm({ farmId, itemId, language, onUploaded, defaultPestCode = 'OTHER' }: { defaultPestCode?: string; farmId: string; itemId: string; language: Language; onUploaded: () => void }) {
  const [state, setState] = useState<{ kind: 'idle' | 'sending' | 'success' | 'error'; message: string }>({ kind: 'idle', message: '' });

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = new FormData(form);
    body.set('farmId', farmId);
    body.set('itemId', itemId);
    setState({ kind: 'sending', message: translate(language, 'upload.photoSending') });
    try {
      const response = await fetch('/api/pest-capture', { method: 'POST', body });
      await response.json();
      if (!response.ok) throw new Error(translate(language, 'upload.photoError'));
      form.reset();
      setState({ kind: 'success', message: translate(language, 'upload.photoSuccess') });
      onUploaded();
    } catch (error) {
      setState({ kind: 'error', message: error instanceof Error ? error.message : translate(language, 'upload.photoError') });
    }
  }

  return (
    <form className="mite-capture-form" onSubmit={submit}>
      <label><span>{pestText(language, 'target')}</span><select name="pestCode" defaultValue={defaultPestCode} required>{pestTargets.map((target) => <option value={target.code} key={target.code}>{pestLabel(target.code, language)}</option>)}</select></label>
      <p>{pestText(language, 'unknownHelp')} {pestText(language, 'scope')}</p>
      <label><span>{translate(language, 'upload.rgb')} <b>{translate(language, 'upload.required')}</b></span><input accept="image/*" capture="environment" name="rgbImage" required type="file" /></label>
      <label><span>{translate(language, 'upload.thermal')} <small>{translate(language, 'common.optional')}</small></span><input accept="image/*" name="thermalImage" type="file" /></label>
      <p>{translate(language, 'upload.photoHelp')}</p>
      <button disabled={!farmId || state.kind === 'sending'} type="submit">{state.kind === 'sending' ? translate(language, 'common.loading') : translate(language, 'upload.submit')}</button>
      {state.kind !== 'idle' && <div className={`upload-status ${state.kind}`} role="status">{state.message}</div>}
    </form>
  );
}
