'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { asLanguage, type Language } from '@/app/lib/i18n';
import { NotificationCenter } from './NotificationCenter';

function currentFarmId() {
  if (typeof document === 'undefined') return '';
  const select = document.querySelector<HTMLSelectElement>('.farm-select-wrap select');
  return select?.value?.trim() ?? '';
}

function currentLanguage() {
  if (typeof document === 'undefined') return 'ko' as Language;
  const select = document.querySelector<HTMLSelectElement>('.language-select select');
  return asLanguage(select?.value || window.localStorage.getItem('farm-language') || 'ko');
}

export function NotificationBridge() {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [farmId, setFarmId] = useState('');
  const [language, setLanguage] = useState<Language>('ko');

  useEffect(() => {
    let observer: MutationObserver | null = null;

    const sync = () => {
      const nextHost = document.querySelector<HTMLElement>('.app-topbar');
      setHost(nextHost);
      setFarmId(currentFarmId());
      setLanguage(currentLanguage());
    };

    const handleChange = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement)) return;
      if (target.matches('.farm-select-wrap select, .language-select select')) sync();
    };

    sync();
    document.addEventListener('change', handleChange);
    observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      document.removeEventListener('change', handleChange);
      observer?.disconnect();
    };
  }, []);

  function openScouting(locationStateId: string) {
    const url = new URL(window.location.href);
    url.searchParams.set('screen', 'alerts');
    url.searchParams.set('scoutingLocation', locationStateId);
    window.location.assign(url.toString());
  }

  if (!host) return null;
  return createPortal(
    <NotificationCenter farmId={farmId} language={language} onOpenScouting={openScouting} />,
    host,
  );
}
