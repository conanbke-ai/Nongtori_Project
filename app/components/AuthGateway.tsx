'use client';

import Image from 'next/image';
import { NongtoriPortrait } from '@/app/ui/tori/NongtoriPortrait';
import { FormEvent, useState } from 'react';
import { asLanguage, languageNames, languages, translate, type Language } from '@/app/lib/i18n';

type AuthMode = 'signin' | 'worker-signup' | 'pending';
type Provider = 'kakao' | 'naver' | 'google';

const providers: { id: Provider; label: string; mark: string }[] = [
  { id: 'kakao', label: 'Kakao', mark: 'K' },
  { id: 'naver', label: 'NAVER', mark: 'N' },
  { id: 'google', label: 'Google', mark: 'G' },
];

export function AuthGateway({ preview = false }: { preview?: boolean }) {
  const [language, setLanguage] = useState<Language>('ko');
  const [countryCode, setCountryCode] = useState('+82');
  const [mode, setMode] = useState<AuthMode>('signin');
  const [notice, setNotice] = useState('');
  const [termsAccepted, setTermsAccepted] = useState(false);

  function providerNotice(provider: Provider) {
    const providerName = providers.find((item) => item.id === provider)?.label ?? provider;
    setNotice(translate(language, 'auth.providerSetup', { provider: providerName }));
  }

  function changeLanguage(next: Language) {
    setLanguage(next);
    setCountryCode(next === 'vi' ? '+84' : next === 'th' ? '+66' : next === 'zh-CN' ? '+86' : '+82');
    setNotice('');
  }

  function previewWorkerRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!termsAccepted) {
      setNotice(translate(language, 'auth.termsRequired'));
      return;
    }
    setNotice('');
    setMode('pending');
  }

  return (
    <main className="auth-gateway">
      <section className="auth-shell">
        <aside className="auth-visual-panel">
          <div className="auth-brand"><span aria-hidden="true" className="auth-brand-icon"><Image alt="" fill priority sizes="38px" src="/nongtori-app-icon-512.png" /></span><strong>{translate(language, 'auth.serviceName')}</strong></div>
          <div className="auth-visual-copy">
            <span>{translate(language, 'auth.eyebrow')}</span>
            <h1>{translate(language, 'auth.welcomeTitle')}</h1>
            <p>{translate(language, 'auth.welcomeDesc')}</p>
          </div>
          <div className="auth-nongtori"><NongtoriPortrait alt={translate(language, 'scout.alt')} /></div>
          <div className="auth-trust-list"><span>{translate(language, 'auth.trustFarm')}</span><span>{translate(language, 'auth.trustLanguage')}</span><span>{translate(language, 'auth.trustRoles')}</span></div>
        </aside>

        <section className="auth-form-panel">
          <header className="auth-form-header">
            <div><span>{translate(language, 'auth.language')}</span><strong>{languageNames[language]}</strong></div>
            <select aria-label={translate(language, 'auth.language')} onChange={(event) => changeLanguage(asLanguage(event.target.value))} value={language}>
              {languages.map((item) => <option key={item} value={item}>{languageNames[item]}</option>)}
            </select>
          </header>

          {preview && <div className="auth-preview-notice"><strong>{translate(language, 'auth.previewTitle')}</strong><span>{translate(language, 'auth.previewDesc')}</span></div>}

          {mode === 'signin' && (
            <div className="auth-view auth-signin-view">
              <div className="auth-view-heading"><span>{translate(language, 'auth.ownerAdmin')}</span><h2>{translate(language, 'auth.signinTitle')}</h2><p>{translate(language, 'auth.signinDesc')}</p></div>
              <div className="social-login-list">
                {providers.map((provider) => <button className={`social-login ${provider.id}`} disabled={!preview} key={provider.id} onClick={() => providerNotice(provider.id)} type="button"><i aria-hidden="true">{provider.mark}</i><span>{translate(language, 'auth.continueWith', { provider: provider.label })}</span><small>{translate(language, 'auth.setupNeeded')}</small></button>)}
              </div>
              <div className="auth-divider"><span>{translate(language, 'auth.currentOperation')}</span></div>
              <a className="sites-login-button" href="/signin-with-chatgpt?return_to=%2F">{translate(language, 'auth.currentLogin')}</a>
              <div className="worker-entry-card"><div><span>{translate(language, 'auth.worker')}</span><strong>{translate(language, 'auth.workerQuestion')}</strong><p>{translate(language, 'auth.workerEntryDesc')}</p></div><div><button onClick={() => { setMode('worker-signup'); setNotice(''); }} type="button">{translate(language, 'auth.workerSignup')}</button><button className="text-button" onClick={() => setNotice(translate(language, 'auth.workerLoginSetup'))} type="button">{translate(language, 'auth.workerLogin')}</button></div></div>
            </div>
          )}

          {mode === 'worker-signup' && (
            <form className="auth-view worker-signup-form" onSubmit={previewWorkerRequest}>
              <button className="auth-back" onClick={() => { setMode('signin'); setNotice(''); }} type="button">← {translate(language, 'auth.back')}</button>
              <div className="auth-view-heading"><span>{translate(language, 'auth.workerSignup')}</span><h2>{translate(language, 'auth.workerSignupTitle')}</h2><p>{translate(language, 'auth.workerSignupDesc')}</p></div>
              <ol className="signup-steps" aria-label={translate(language, 'auth.signupSteps')}><li className="active"><b>1</b><span>{translate(language, 'auth.stepInvite')}</span></li><li><b>2</b><span>{translate(language, 'auth.stepVerify')}</span></li><li><b>3</b><span>{translate(language, 'auth.stepApproval')}</span></li></ol>
              <label><span>{translate(language, 'auth.inviteCode')}</span><input autoComplete="one-time-code" maxLength={12} name="inviteCode" placeholder={translate(language, 'auth.invitePlaceholder')} required /></label>
              <label><span>{translate(language, 'auth.name')}</span><input autoComplete="name" maxLength={50} name="displayName" placeholder={translate(language, 'auth.namePlaceholder')} required /></label>
              <div className="international-phone-field"><label><span>{translate(language, 'auth.countryCode')}</span><select name="countryCode" onChange={(event) => setCountryCode(event.target.value)} value={countryCode}><option value="+82">한국 +82</option><option value="+84">Việt Nam +84</option><option value="+66">ไทย +66</option><option value="+86">中国 +86</option></select></label><label><span>{translate(language, 'auth.phone')}</span><input autoComplete="tel-national" inputMode="tel" name="phone" placeholder="10 123 4567" required /></label></div>
              <label><span>{translate(language, 'auth.preferredLanguage')}</span><select name="preferredLanguage" onChange={(event) => changeLanguage(asLanguage(event.target.value))} value={language}>{languages.map((item) => <option key={item} value={item}>{languageNames[item]}</option>)}</select></label>
              <label className="auth-terms"><input checked={termsAccepted} onChange={(event) => setTermsAccepted(event.target.checked)} type="checkbox" /><span>{translate(language, 'auth.terms')}</span></label>
              <p className="worker-form-note">{translate(language, 'auth.noFarmId')}</p>
              <button className="worker-request-button" type="submit">{translate(language, 'auth.previewRequest')}</button>
            </form>
          )}

          {mode === 'pending' && (
            <div className="auth-view auth-pending-view">
              <div className="pending-mark" aria-hidden="true">✓</div>
              <span>{translate(language, 'auth.workerSignup')}</span><h2>{translate(language, 'auth.pendingTitle')}</h2><p>{translate(language, 'auth.pendingDesc')}</p>
              <div><strong>{translate(language, 'auth.pendingFlowTitle')}</strong><ol><li>{translate(language, 'auth.pendingFlowVerify')}</li><li>{translate(language, 'auth.pendingFlowOwner')}</li><li>{translate(language, 'auth.pendingFlowLogin')}</li></ol></div>
              <button onClick={() => setMode('signin')} type="button">{translate(language, 'auth.backToLogin')}</button>
            </div>
          )}

          {notice && <div className="auth-inline-notice" role="status">{notice}</div>}
          <footer>{translate(language, 'auth.securityFooter')}</footer>
        </section>
      </section>
    </main>
  );
}
