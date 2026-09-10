'use client';

import { useEffect, useState } from 'react';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function PwaInstallButton() {
  const [promptEvent, setPromptEvent] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const [showGuide, setShowGuide] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setInstalled(window.matchMedia('(display-mode: standalone)').matches
      || Boolean((navigator as Navigator & { standalone?: boolean }).standalone)), 0);
    if ('serviceWorker' in navigator) void navigator.serviceWorker.register('/sw.js');
    const handler = (event: Event) => {
      event.preventDefault();
      setPromptEvent(event as InstallPromptEvent);
    };
    window.addEventListener('beforeinstallprompt', handler);
    window.addEventListener('appinstalled', () => setInstalled(true), { once: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('beforeinstallprompt', handler);
    };
  }, []);

  async function install() {
    if (!promptEvent) {
      setShowGuide(true);
      return;
    }
    await promptEvent.prompt();
    const choice = await promptEvent.userChoice;
    if (choice.outcome === 'accepted') setInstalled(true);
    setPromptEvent(null);
  }

  if (installed) return <span className="installed-badge">앱으로 실행 중</span>;

  return (
    <>
      <button className="install-button" onClick={install} type="button">앱 설치</button>
      {showGuide && (
        <div className="install-guide" role="dialog" aria-modal="true" aria-label="앱 설치 방법">
          <div><strong>홈 화면에 앱 추가</strong><p>브라우저 메뉴에서 <b>홈 화면에 추가</b> 또는 <b>앱 설치</b>를 선택해 주세요.</p><button onClick={() => setShowGuide(false)} type="button">확인</button></div>
        </div>
      )}
    </>
  );
}
