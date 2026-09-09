'use client';

import Image from 'next/image';
import { NongtoriPortrait } from '@/app/ui/tori/NongtoriPortrait';
import { PestOverviewCard, activePestSummary, type OverviewState } from '@/app/features/pests/presentation/PestOverviewCard';
import '@/app/features/pests/presentation/overview.css';
import { pestTargets, pestLabel } from '@/app/features/pests/domain/catalog';
import { recordText } from '@/app/features/records/presentation/text';
import { pestText } from '@/app/features/pests/presentation/text';
import '@/app/features/pests/presentation/pests.css';
import { useEffect, useMemo, useRef, useState } from 'react';
import { AccountCenter, type AccountRecord } from './AccountCenter';
import { AuthGateway } from './AuthGateway';
import { CameraCapture } from './CameraCapture';
import { CropGuideLibrary, type CropGuideRecord } from './CropGuideLibrary';
import { FarmMiniChat } from './FarmMiniChat';
import { FarmStatus } from './FarmStatus';
import { HarvestLog } from './HarvestLog';
import { PestCaptureForm } from './PestCaptureForm';
import { PestAlertReview, type PestAlertPagination, type PestAlertRecord } from './PestAlertReview';
import { RecordNotes } from './RecordNotes';
import { PwaInstallButton } from './PwaInstallButton';
import { RevenueForecast, type ForecastJobRecord, type RevenueForecastRecord } from './RevenueForecast';
import { VideoUploadForm } from './VideoUploadForm';
import { asLanguage, languageNames, languages, localeForLanguage, translate, type Language } from '@/app/lib/i18n';

type Screen = 'home' | 'alerts' | 'history' | 'capture' | 'guide' | 'management' | 'account';
type Farm = { id: string; name: string; timezone: string };
type FarmItem = { id: string; crop_code: string; crop_name: string; cultivar_code: string | null; cultivar_name: string | null; display_name: string; crop_image_uri: string | null; crop_description: string | null };
type Camera = {
  id: string; name: string; camera_type: string; source_type: string; status: string;
  connection_status: string; last_seen_at: string | null;
};
type Session = {
  id: string; source_type: string; processing_status: string; started_at: string;
  camera_name: string | null; house_name: string | null; bed_name: string | null; zone_name: string | null;
};
type HistoryRecord = Session & {
  pest_code: string | null; note_count: number;
  item_id: string | null; capture_mode: string; ended_at: string | null; item_name: string | null;
  crop_name: string | null; cultivar_name: string | null;
};
type HistoryResponse = { rows: HistoryRecord[]; total: number; page: number; limit: number; pageCount: number };
type PestBreakdown = { code: string; label: string; openCount: number; capability: 'RECORD_ONLY' };
type DashboardData = {
  farms: Farm[];
  account: AccountRecord;
  selectedFarm: Farm | null;
  summary: { robotCount: number; todayRecordedSessions: number; alertCount: number; pestBreakdown: PestBreakdown[]; harvestCandidates: number; pendingSessions: number };
  cameras: Camera[];
  alerts: PestAlertRecord[];
  alertPagination: PestAlertPagination;
  recentSessions: Session[];
  pendingSessionsByItem: { item_id: string | null; count: number }[];
  items: FarmItem[];
  guides: CropGuideRecord[];
  revenueForecasts?: RevenueForecastRecord[];
  forecastJobs?: ForecastJobRecord[];
  setupRequired: boolean;
  membershipRequired: boolean;
};

const emptyData: DashboardData = {
  farms: [], account: {
    authenticated: true, loginId: null, email: null, displayName: null, publicName: null, accountCode: null,
    phone: null, phoneVerified: false,
    notificationsEnabled: false, preferredLanguage: 'ko', role: null, roleLabel: null,
    permissions: { viewRevenue: false, manageMembers: false, manageFarm: false, uploadMedia: false, reviewAlerts: false, viewHistory: false },
    loginManagedExternally: true,
  }, selectedFarm: null,
  summary: { robotCount: 0, todayRecordedSessions: 0, alertCount: 0, pestBreakdown: pestTargets.map((target) => ({ code: target.code, label: target.labels.ko, openCount: 0, capability: target.capability })), harvestCandidates: 0, pendingSessions: 0 },
  cameras: [], alerts: [], alertPagination: { status: 'OPEN', page: 1, limit: 20, total: 0, pageCount: 0, openCount: 0, doneCount: 0 }, recentSessions: [], pendingSessionsByItem: [], items: [], guides: [], setupRequired: true, membershipRequired: false,
};

const menu: { id: Exclude<Screen, 'account'>; icon: string }[] = [
  { id: 'home', icon: '01' },
  { id: 'capture', icon: '02' },
  { id: 'alerts', icon: '03' },
  { id: 'history', icon: '04' },
  { id: 'guide', icon: '05' },
  { id: 'management', icon: '06' },
];

const menuKeys = {
  home: 'menu.home',
  capture: 'menu.capture',
  alerts: 'menu.alerts',
  history: 'menu.history',
  guide: 'menu.guide',
} as const;

const mobileMenuKeys = {
  home: 'menu.mobileHome',
  capture: 'menu.mobileCapture',
  alerts: 'menu.mobileAlerts',
  history: 'menu.mobileHistory',
  guide: 'menu.mobileGuide',
  management: 'menu.mobileManagement',
} as const;

function localDateKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function dateDaysAgo(days: number) {
  const value = new Date();
  value.setDate(value.getDate() - days);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
}

function formatDate(language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
}

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

function sessionStatus(status: string, language: Language) {
  const labels: Record<string, Parameters<typeof translate>[1]> = {
    REGISTERED: 'status.registered', PROCESSING: 'status.processing', COMPLETED: 'status.completed', FAILED: 'status.failed',
    UPLOADED_AWAITING_MODEL: 'status.awaitingModel', UPLOADED_AWAITING_FRAME_EXTRACTION: 'status.extractingFrames',
  };
  return labels[status] ? translate(language, labels[status]) : status;
}

async function requestDashboard(selectedFarmId = '', alertStatus: 'OPEN' | 'DONE' = 'OPEN', alertPage = 1, pestCode = '') {
  const params = new URLSearchParams({ date: localDateKey() });
  if (selectedFarmId) params.set('farmId', selectedFarmId);
  params.set('alertStatus', alertStatus);
  params.set('alertPage', String(alertPage));
  if (pestCode) params.set('pestCode', pestCode);
  const response = await fetch(`/api/farmer-dashboard?${params}`, { cache: 'no-store' });
  if (!response.ok) throw new Error('농장 정보를 불러오지 못했습니다.');
  return response.json() as Promise<DashboardData>;
}

export function FarmerDashboard() {
  const [screen, setScreen] = useState<Screen>('home');
  const [data, setData] = useState<DashboardData>(emptyData);
  const [farmId, setFarmId] = useState('');
  const [itemId, setItemId] = useState('');
  const [fruitTab, setFruitTab] = useState<'video' | 'photo' | 'forecast'>('video');
  const [pestTab, setPestTab] = useState<'status' | 'photo'>('status');
  const [managementTab, setManagementTab] = useState<'overview' | 'harvest'>('overview');
  const [pestCode, setPestCode] = useState('');
  const dashboardRequestSequence = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [historyFrom, setHistoryFrom] = useState(() => dateDaysAgo(30));
  const [historyTo, setHistoryTo] = useState(() => localDateKey());
  const [historySource, setHistorySource] = useState('');
  const [historyStatus, setHistoryStatus] = useState('');
  const [history, setHistory] = useState<HistoryResponse>({ rows: [], total: 0, page: 1, limit: 30, pageCount: 0 });
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [language, setLanguage] = useState<Language>('ko');
  const [pageEdge, setPageEdge] = useState({ top: true, bottom: false });
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = new URLSearchParams(window.location.search).get('screen');
      if ([...menu.map((item) => item.id), 'account'].includes(value as Screen)) setScreen(value as Screen);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    function updatePageEdge() {
      const top = window.scrollY <= 24;
      const bottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 24;
      setPageEdge((current) => current.top === top && current.bottom === bottom ? current : { top, bottom });
    }
    updatePageEdge();
    window.addEventListener('scroll', updatePageEdge, { passive: true });
    window.addEventListener('resize', updatePageEdge);
    return () => {
      window.removeEventListener('scroll', updatePageEdge);
      window.removeEventListener('resize', updatePageEdge);
    };
  }, [screen, loading]);

  function apply(next: DashboardData) {
    setData(next);
    setLoaded(true);
    const storedLanguage = typeof window !== 'undefined' ? window.localStorage.getItem('farm-language') : null;
    setLanguage(asLanguage(storedLanguage || next.account.preferredLanguage));
    if (next.selectedFarm) setFarmId(next.selectedFarm.id);
    if (next.items.length > 0) setItemId((current) => next.items.some((item) => item.id === current) ? current : next.items[0].id);
    setLoading(false);
  }

  function reload(selectedFarmId = farmId, alertStatus: 'OPEN' | 'DONE' = 'OPEN', alertPage = 1, selectedPestCode = pestCode) {
    setLoading(true);
    setError('');
    const sequence = ++dashboardRequestSequence.current;
    void requestDashboard(selectedFarmId, alertStatus, alertPage, selectedPestCode).then((next) => {
      if (sequence === dashboardRequestSequence.current) apply(next);
    }).catch((caught) => {
      if (sequence !== dashboardRequestSequence.current) return;
      setError(caught instanceof Error ? caught.message : '화면을 새로고침해 주세요.');
      setLoading(false);
    });
  }

  useEffect(() => {
    void requestDashboard().then((next) => {
      setData(next);
      setLoaded(true);
      const storedLanguage = window.localStorage.getItem('farm-language');
      setLanguage(asLanguage(storedLanguage || next.account.preferredLanguage));
      if (next.selectedFarm) setFarmId(next.selectedFarm.id);
      if (next.items.length > 0) setItemId(next.items[0].id);
      setLoading(false);
    }).catch((caught) => {
      setError(caught instanceof Error ? caught.message : '화면을 새로고침해 주세요.');
      setLoading(false);
      setLoaded(true);
    });
  }, []);

  const selectedItem = data.items.find((item) => item.id === itemId) ?? data.items[0] ?? null;
  const cropOptions = useMemo(() => Array.from(new Map(data.items.map((item) => [item.crop_code, { code: item.crop_code, name: item.crop_name }])).values()), [data.items]);
  const cultivarOptions = useMemo(() => data.items.filter((item) => item.crop_code === selectedItem?.crop_code), [data.items, selectedItem?.crop_code]);
  const selectedGuides = useMemo(() => data.guides.filter((guide) => guide.crop_code === selectedItem?.crop_code && (!guide.cultivar_code || guide.cultivar_code === selectedItem?.cultivar_code)), [data.guides, selectedItem?.crop_code, selectedItem?.cultivar_code]);
  const selectedModelReady = selectedItem?.crop_code === 'STRAWBERRY' && selectedItem.cultivar_code === 'SEOLHYANG';
  const canViewRevenue = data.account.permissions.viewRevenue;
  const effectiveFruitTab = !canViewRevenue && fruitTab === 'forecast' ? 'video' : fruitTab;
  const accountRoleName = data.account.role === 'ADMIN' ? translate(language, 'role.admin')
    : data.account.role === 'OWNER' ? translate(language, 'role.owner')
      : data.account.role === 'WORKER' ? translate(language, 'role.worker') : '내 계정';
  const accountPublicName = data.account.publicName?.trim() || accountRoleName;
  const accountCode = data.account.accountCode?.trim() ?? '';
  const accountMeta = accountCode && !accountPublicName.includes(accountCode)
    ? `${accountRoleName} · ${accountCode}`
    : accountRoleName;
  const selectedPendingSessions = Number(data.pendingSessionsByItem.find((entry) => entry.item_id === selectedItem?.id)?.count ?? 0);
  const scoutMode = data.summary.alertCount > 0 ? 'alert' : selectedPendingSessions > 0 ? 'pending' : 'ready';
  const scoutTarget: Screen = scoutMode === 'alert' ? 'alerts' : scoutMode === 'pending' ? 'history' : 'capture';
  const scoutTitle = scoutMode === 'alert'
    ? translate(language, 'scout.alertTitle', { count: data.summary.alertCount })
    : scoutMode === 'pending'
      ? translate(language, 'scout.pendingTitle', { count: selectedPendingSessions })
      : translate(language, 'scout.readyTitle');
  const scoutDescription = scoutMode === 'alert' ? pestText(language, 'alertHelp')
    : translate(language, scoutMode === 'pending' ? 'scout.pendingDesc' : 'scout.readyDesc');
  const pestOverviewState: OverviewState = loading ? 'loading' : error ? 'error' : !data.selectedFarm ? 'unlinked' : 'ready';
  const scoutAction = translate(language, scoutMode === 'alert'
    ? 'scout.openAlerts' : scoutMode === 'pending' ? 'scout.openHistory' : 'scout.startAnalysis');
  const selectedItemId = selectedItem?.id ?? '';
  const selectedRevenueForecasts = useMemo(() => (data.revenueForecasts ?? []).filter((forecast) => forecast.item_id === selectedItem?.id), [data.revenueForecasts, selectedItem?.id]);
  const selectedForecastJobs = useMemo(() => (data.forecastJobs ?? []).filter((job) => job.item_id === selectedItem?.id), [data.forecastJobs, selectedItem?.id]);

  async function loadHistory(page = 1) {
    if (!farmId || !selectedItem) return;
    setHistoryLoading(true);
    setHistoryError('');
    const params = new URLSearchParams({ farmId, itemId: selectedItem.id, from: historyFrom, to: historyTo, page: String(page), limit: '30' });
    if (historySource) params.set('sourceType', historySource);
    if (historyStatus) params.set('status', historyStatus);
    try {
      const response = await fetch(`/api/operation-history?${params}`, { cache: 'no-store' });
      const result = await response.json() as HistoryResponse & { error?: string };
      if (!response.ok) throw new Error(result.error ?? '판독 이력을 불러오지 못했습니다.');
      setHistory(result);
    } catch (caught) {
      setHistoryError(caught instanceof Error ? caught.message : '판독 이력을 불러오지 못했습니다.');
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    if (screen !== 'history' || !farmId || !selectedItemId) return;
    let cancelled = false;
    const params = new URLSearchParams({ farmId, itemId: selectedItemId, from: dateDaysAgo(30), to: localDateKey(), page: '1', limit: '30' });
    void Promise.resolve().then(async () => {
      if (cancelled) return;
      setHistoryLoading(true);
      setHistoryError('');
      try {
        const response = await fetch(`/api/operation-history?${params}`, { cache: 'no-store' });
        const result = await response.json() as HistoryResponse & { error?: string };
        if (!response.ok) throw new Error(result.error ?? '판독 이력을 불러오지 못했습니다.');
        if (!cancelled) setHistory(result);
      } catch (caught) {
        if (!cancelled) setHistoryError(caught instanceof Error ? caught.message : '판독 이력을 불러오지 못했습니다.');
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [screen, farmId, selectedItemId]);

  function open(next: Screen) {
    setScreen(next);
    const url = new URL(window.location.href);
    url.searchParams.set('screen', next);
    window.history.replaceState(null, '', url);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function openScoutTarget() {
    if (scoutMode === 'alert') {
      openPestManagement();
      return;
    }
    if (scoutMode === 'ready') setFruitTab('video');
    open(scoutTarget);
  }

  function openPestManagement(targetCode = '') {
    setPestTab('status');
    setPestCode(targetCode);
    open('alerts');
    reload(farmId, 'OPEN', 1, targetCode);
  }

  function changeLanguage(next: Language) {
    setLanguage(next);
    window.localStorage.setItem('farm-language', next);
    if (farmId) {
      void fetch('/api/account-profile', {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, preferredLanguage: next }),
      });
    }
  }

  function scrollPage(target: 'top' | 'bottom') {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({
      top: target === 'top' ? 0 : document.documentElement.scrollHeight,
      behavior: reducedMotion ? 'auto' : 'smooth',
    });
  }

  function openChat() {
    if (!farmId) return;
    setChatOpen(true);
  }

  const navigation = (mobile = false) => (
    <nav className={mobile ? 'mobile-nav' : 'app-menu'} aria-label="주요 메뉴">
      {menu.map((item) => (
        <button className={screen === item.id ? 'selected' : ''} key={item.id} onClick={() => open(item.id)} type="button">
          <span className="menu-number">{item.icon}</span><span className="menu-label">{mobile
            ? translate(language, mobileMenuKeys[item.id])
            : item.id === 'management' ? translate(language, 'menu.management') : translate(language, menuKeys[item.id])}</span>
          {item.id === 'alerts' && data.summary.alertCount > 0 && <b>{data.summary.alertCount}</b>}
        </button>
      ))}
    </nav>
  );

  if (loaded && !data.account.authenticated) {
    return <AuthGateway />;
  }

  return (
    <main className="farmer-app" id="page-top">
      <header className="app-topbar">
        <button className="app-brand" onClick={() => open('home')} type="button"><span aria-hidden="true" className="app-brand-mark"><Image alt="" fill priority sizes="48px" src="/nongtori-app-icon-512.png" /></span><span className="app-brand-copy"><strong>농토리 운영센터</strong><span>재배 · 수확 · 예찰을 한곳에서</span></span></button>
        <div className="app-context-selectors">
          <label className="farm-select-wrap"><span>{translate(language, 'common.farm')}</span><select disabled={data.farms.length === 0} onChange={(event) => { setFarmId(event.target.value); setItemId(''); reload(event.target.value); }} value={farmId}>{data.farms.length === 0 && <option value="">연결된 농장 없음</option>}{data.farms.map((farm) => <option key={farm.id} value={farm.id}>{farm.name}</option>)}</select></label>
          <label className="crop-select-wrap"><span>{translate(language, 'common.crop')}</span><select disabled={cropOptions.length === 0} onChange={(event) => { const nextItem = data.items.find((item) => item.crop_code === event.target.value); if (nextItem) setItemId(nextItem.id); }} value={selectedItem?.crop_code ?? ''}>{cropOptions.length === 0 && <option value="">작물 없음</option>}{cropOptions.map((crop) => <option key={crop.code} value={crop.code}>{crop.name}</option>)}</select></label>
          <label className="item-select-wrap"><span>{translate(language, 'common.cultivar')}</span><select disabled={cultivarOptions.length === 0} onChange={(event) => setItemId(event.target.value)} value={selectedItem?.id ?? ''}>{cultivarOptions.length === 0 && <option value="">품종 없음</option>}{cultivarOptions.map((item) => <option key={item.id} value={item.id}>{item.cultivar_name ?? item.display_name}</option>)}</select></label>
        </div>
        <label className="language-select"><span>{translate(language, 'common.language')}</span><select aria-label={translate(language, 'common.language')} onChange={(event) => changeLanguage(asLanguage(event.target.value))} value={language}>{languages.map((item) => <option key={item} value={item}>{languageNames[item]}</option>)}</select></label>
        <button className="refresh-button" disabled={loading} onClick={() => reload()} type="button">{loading ? translate(language, 'common.loading') : translate(language, 'common.refresh')}</button>
        <PwaInstallButton />
        <button className="user-button" aria-label={`${accountPublicName} 계정`} onClick={() => open('account')} title={`${accountPublicName} · ${accountMeta}`} type="button"><span>{accountPublicName.slice(0, 1).toUpperCase() || '농'}</span><span className="user-button-copy"><b>{accountPublicName}</b><small>{accountMeta}</small></span></button>
      </header>

      <aside className="app-sidebar">
        {navigation()}
        <button className="sidebar-chat-entry" disabled={!farmId} onClick={openChat} type="button"><span aria-hidden="true">•••</span><div><strong>{translate(language, 'chat.open')}</strong><small>{farmId ? translate(language, 'chat.sidebarHelp') : translate(language, 'chat.unavailable')}</small></div></button>
        <div className="sidebar-device"><i className="online" /><div><strong>저장 영상 판독</strong><span>일반·열화상 영상 지원</span></div></div>
      </aside>

      <div className="app-content">
        {error && <div className="error-banner" role="alert"><strong>{error}</strong><button onClick={() => reload()} type="button">다시 시도</button></div>}
        {loaded && data.membershipRequired && data.farms.length === 0 && (
          <div className="account-link-banner"><strong>계약 농장 연결 대기</strong><span>이 로그인 계정에 농장 정보가 등록되면 자동으로 표시됩니다.</span></div>
        )}
        <>
            {screen === 'home' && (
              <section className="app-screen home-screen">
                <div className="screen-heading overview-heading"><div><p>{formatDate(language)}</p><h1>{translate(language, 'home.title')}</h1><span>{data.selectedFarm?.name ?? '농장 연결 대기'} · {selectedItem?.display_name ?? '재배 품목 연결 대기'}</span></div><button className="primary-action" onClick={() => open('capture')} type="button">{translate(language, 'upload.savedVideo')}</button></div>
                {data.setupRequired && <div className="setup-banner"><span>!</span><div><strong>계약 정보 연결 대기</strong><p>업체가 농장·품목 정보를 등록하면 이 계정에 자동으로 연결됩니다.</p></div></div>}
                <article className={`nongtori-overview ${scoutMode}`}>
                  <div className="nongtori-overview-copy">
                    <span className="nongtori-kicker"><i aria-hidden="true">●</i>{translate(language, 'home.nongtoriBriefing')}</span>
                    <h2>{scoutTitle}</h2>
                    <p>{scoutDescription}</p>
                    {scoutMode === 'alert' ? <div className="nongtori-context-row">
                      <span><small>{translate(language, 'home.scopeLabel')}</small><b>{translate(language, 'home.farmWideScope')}</b></span>
                      <span className="pest-context"><small>{pestText(language, 'reviewNeeded')}</small><b>{activePestSummary(data.summary.pestBreakdown, language)}</b></span>
                    </div> : <div className="nongtori-context-row">
                      <span><small>{translate(language, 'common.crop')}</small><b>{selectedItem?.crop_name ?? '연결 대기'}</b></span>
                      <span><small>{translate(language, 'common.cultivar')}</small><b>{selectedItem?.cultivar_name ?? '미지정'}</b></span>
                      <span className={selectedModelReady ? 'model-ready' : ''}><small>AI 판독</small><b>{selectedModelReady ? '설향 사용 가능' : '준비 중'}</b></span>
                    </div>}
                    <div className="scout-sensor-tags"><span>{translate(language, 'alert.regularTogether')}</span><span>{translate(language, 'alert.thermalPrimary')}</span></div>
                    <button onClick={openScoutTarget} type="button">{scoutAction}</button>
                  </div>
                  <div className="nongtori-overview-art"><NongtoriPortrait alt={translate(language, 'scout.alt')} /></div>
                  <div className="nongtori-metrics">
                    <article><span><small>{translate(language, 'home.farmWideScope')}</small>{translate(language, 'home.todaySubmissions')}</span><div><strong>{data.summary.todayRecordedSessions}</strong><small>{translate(language, 'common.cases')}</small></div></article>
                    <article><span><small>{translate(language, 'home.farmWideScope')}</small>{translate(language, 'home.gradeCompleted')}</span><div><strong>{data.summary.harvestCandidates}</strong><small>{translate(language, 'harvest.pieces')}</small></div></article>
                    <article className={`pest-summary-metric ${data.summary.alertCount > 0 ? 'attention' : ''}`}>
                      <details><summary><span><small>{translate(language, 'home.farmWideScope')}</small>{translate(language, 'home.miteReviewNeeded')}</span><div><strong>{data.summary.alertCount}</strong><small>{translate(language, 'common.cases')}</small></div></summary><div className="pest-breakdown-list"><span>{translate(language, 'home.farmWidePest')}</span>{data.summary.pestBreakdown.map((target) => <button key={target.code} onClick={() => openPestManagement(target.code)} type="button"><span>{pestLabel(target.code, language)}</span><b>{target.openCount}{translate(language, 'common.cases')}</b><small>{pestText(language, 'recordOnly')}</small></button>)}</div></details>
                    </article>
                  </div>
                </article>
                <div className="workflow-grid">
                  <article className="workflow-card fruit-workflow"><header><span>수확 후 품질 관리</span><b>01</b></header><h2>수확 과실 영상 판독</h2><p>촬영한 일반 영상을 장면별로 나누어 딸기의 익은 정도와 품질 등급을 살핍니다. 같은 딸기가 여러 장면에 보여도 한 개로 계산합니다.</p><div className="workflow-tags"><span>일반 영상</span><span>익은 정도</span><span>품질 등급</span></div><div className="fruit-workflow-illustration" aria-hidden="true"><svg viewBox="0 0 110 100" fill="none"><rect x="8" y="10" width="94" height="78" rx="18" fill="white" stroke="#efc4cb" strokeWidth="1.5"/><path d="M34 38c-7-9-16 1-11 12l15 20c3 4 7 4 10 0l15-20c5-11-4-21-11-12-5-7-13-7-18 0Z" fill="var(--tori-strawberry)"/><path d="m35 30 8 8 9-8m-9 8V24" stroke="var(--tori-field)" strokeWidth="3" strokeLinecap="round"/><path d="m31 47 1 3m12-5v3m10 1-1 3m-14 6 1 3m7-3-1 3" stroke="white" strokeWidth="2" strokeLinecap="round"/><path d="M73 37h14m-14 10h10m-10 10h14" stroke="var(--tori-primary-deep)" strokeWidth="3" strokeLinecap="round"/><circle cx="87" cy="74" r="13" fill="var(--tori-field)"/><path d="m81 74 4 4 8-8" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/></svg></div><footer><div><span>{translate(language, 'home.fruitWorkflowScope')}</span><strong>{data.summary.harvestCandidates}개</strong></div><button onClick={() => open('capture')} type="button">영상 접수</button></footer></article>
                  <PestOverviewCard targets={data.summary.pestBreakdown} total={data.summary.alertCount} language={language} state={pestOverviewState} onSelect={openPestManagement} />
                </div>
              </section>
            )}

            {screen === 'alerts' && (
              <section className="app-screen pest-screen">
                <div className="screen-heading"><div><p>{translate(language, 'menu.alerts')}</p><h1>{pestText(language, 'managementTitle')}</h1><span>{data.selectedFarm?.name ?? translate(language, 'common.farm')} · {translate(language, 'pest.farmWide')}</span></div><button className="primary-action" onClick={() => open('capture')} type="button">{translate(language, 'upload.submit')}</button></div>
                <div className="pest-category-overview"><div><span>{translate(language, 'pest.totalOpen')}</span><strong>{data.summary.alertCount}{translate(language, 'common.cases')}</strong><small>{translate(language, 'pest.farmWide')}</small></div><p>{pestText(language, 'scope')}</p></div>
                <div className="pest-target-filters" role="group" aria-label={pestText(language, 'target')}>
                  <button aria-pressed={!pestCode} type="button" onClick={() => { setPestCode(''); reload(farmId, 'OPEN', 1, ''); }}>{pestText(language, 'all')}<b>{data.summary.alertCount}</b></button>
                  {data.summary.pestBreakdown.map((target) => <button key={target.code} aria-pressed={pestCode === target.code} type="button" onClick={() => { setPestCode(target.code); reload(farmId, 'OPEN', 1, target.code); }}><strong>{pestLabel(target.code, language)}</strong><b>{target.openCount}</b><small>{pestText(language, 'recordOnly')}</small></button>)}
                </div>
                <div className="module-tabs"><button className={pestTab === 'status' ? 'selected' : ''} onClick={() => setPestTab('status')} type="button">{translate(language, 'alert.open')}</button><button className={pestTab === 'photo' ? 'selected' : ''} onClick={() => setPestTab('photo')} type="button">{translate(language, 'upload.photo')}</button></div>
                {pestTab === 'status' && <PestAlertReview alerts={data.alerts} canReview={data.account.permissions.reviewAlerts} farmId={farmId} key={`${farmId}:${pestCode}`} language={language} onPageChange={(status, page) => reload(farmId, status, page)} onReviewed={() => reload(farmId, data.alertPagination.status, 1)} pagination={data.alertPagination} />}
                {pestTab === 'photo' && <div className="module-workspace"><div className="workspace-heading"><span>가지고 있는 사진 사용</span><h2>일반 잎 사진과 열화상 사진 접수</h2><p>같은 잎을 비슷한 위치에서 찍은 일반 사진과 열화상을 한 번에 올립니다. 열화상이 없어도 일반 사진만 올릴 수 있습니다.</p></div>{farmId && selectedItem ? <PestCaptureForm defaultPestCode={pestCode || 'OTHER'} key={`${farmId}:${selectedItem.id}:${pestCode}`} farmId={farmId} itemId={selectedItem.id} language={language} onUploaded={() => reload()} /> : <div className="screen-empty compact"><strong>농장과 품목 연결이 필요합니다.</strong></div>}</div>}
                <p className="capture-safety"><strong>{translate(language, 'alert.safetyTitle')}</strong> {translate(language, 'alert.safetyText')}</p>
              </section>
            )}

            {screen === 'guide' && (
              <section className="app-screen guide-screen"><div className="screen-heading"><div><p>작기별 병해충 정보</p><h1>작물 가이드</h1><span>{selectedItem ? `${selectedItem.crop_name} · ${selectedItem.cultivar_name ?? '품종 미지정'}` : '농장 연결 전에도 공통 정보를 볼 수 있습니다'}</span></div></div>{data.guides.length > 0 ? <CropGuideLibrary guides={selectedItem ? selectedGuides : data.guides} itemName={selectedItem?.display_name ?? '작물별'} /> : <div className="module-workspace screen-empty"><strong>등록된 작물 정보가 없습니다.</strong><p>작물별 안내가 등록되면 이 화면에 표시됩니다.</p></div>}<p className="capture-safety"><strong>안전 안내</strong> 증상만으로 병해충을 단정하지 마세요. 방제 전에는 해당 작물에 등록된 제품인지와 제품 표시사항·안전사용기준을 공식 정보에서 다시 확인해 주세요.</p></section>
            )}

            {screen === 'history' && (
              <section className="app-screen history-screen">
                <div className="screen-heading"><div><p>날짜별 작업 기록</p><h1>{translate(language, 'screen.historyTitle')}</h1><span>{selectedItem?.display_name ?? '전체 품목'}</span></div></div>
                <p className="data-scope-note">{recordText(language, 'commentsHelp')}</p>
                  <form className="history-filters" onSubmit={(event) => { event.preventDefault(); void loadHistory(1); }}><label><span>{translate(language, 'history.startDate')}</span><input max={historyTo} onChange={(event) => setHistoryFrom(event.target.value)} type="date" value={historyFrom} /></label><label><span>{translate(language, 'history.endDate')}</span><input min={historyFrom} onChange={(event) => setHistoryTo(event.target.value)} type="date" value={historyTo} /></label><label><span>{translate(language, 'history.source')}</span><select onChange={(event) => setHistorySource(event.target.value)} value={historySource}><option value="">{translate(language, 'common.all')}</option><option value="VIDEO_IMPORT">{translate(language, 'history.sourceSavedVideo')}</option><option value="PERSONAL_CAPTURE">{translate(language, 'history.sourceDirectCapture')}</option></select></label><label><span>{translate(language, 'history.status')}</span><select onChange={(event) => setHistoryStatus(event.target.value)} value={historyStatus}><option value="">{translate(language, 'common.all')}</option><option value="REGISTERED">{sessionStatus('REGISTERED', language)}</option><option value="PROCESSING">{sessionStatus('PROCESSING', language)}</option><option value="COMPLETED">{sessionStatus('COMPLETED', language)}</option><option value="FAILED">{sessionStatus('FAILED', language)}</option><option value="UPLOADED_AWAITING_MODEL">{sessionStatus('UPLOADED_AWAITING_MODEL', language)}</option><option value="UPLOADED_AWAITING_FRAME_EXTRACTION">{sessionStatus('UPLOADED_AWAITING_FRAME_EXTRACTION', language)}</option></select></label><button disabled={historyLoading || !farmId || !selectedItem} type="submit">{translate(language, historyLoading ? 'history.searching' : 'history.search')}</button></form>
                  {historyError && <div className="history-error" role="alert">{historyError}</div>}
                  <div className="history-result-heading"><strong>{translate(language, 'history.resultCount', { count: history.total.toLocaleString(localeForLanguage(language)) })}</strong><span>{translate(language, 'history.selectedCultivarBasis')}</span></div>
                  <div className="history-list">{historyLoading ? <div className="screen-empty"><strong>{translate(language, 'history.loading')}</strong></div> : history.rows.length === 0 ? <div className="screen-empty"><span>≡</span><strong>{translate(language, 'history.empty')}</strong><p>{translate(language, 'history.emptyHelp')}</p></div> : history.rows.map((session) => <article key={session.id}><span>{session.source_type === 'VIDEO_IMPORT' ? '▣' : '◎'}</span><div><strong>{session.source_type === 'VIDEO_IMPORT' ? session.capture_mode === 'COMBINED_VIDEO' ? translate(language, 'history.sourceCombined') : translate(language, 'history.sourceSavedVideo') : translate(language, 'history.sourceDirectCapture')}</strong><p>{[session.pest_code ? pestLabel(session.pest_code, language) : null, session.item_name, session.house_name, session.bed_name, session.zone_name].filter(Boolean).join(' · ') || data.selectedFarm?.name}</p></div><time>{formatTime(session.started_at, language)}</time><b>{sessionStatus(session.processing_status, language)}</b><RecordNotes canWrite={data.account.permissions.reviewAlerts} farmId={farmId} language={language} sessionId={session.id} initialCount={session.note_count} />{session.source_type === 'VIDEO_IMPORT' && <RecordNotes canWrite={data.account.permissions.reviewAlerts} farmId={farmId} frameMode language={language} sessionId={session.id} />}</article>)}</div>
                  {history.pageCount > 1 && <div className="history-pagination"><button disabled={history.page <= 1 || historyLoading} onClick={() => void loadHistory(history.page - 1)} type="button">{translate(language, 'common.previous')}</button><span>{history.page} / {history.pageCount}</span><button disabled={history.page >= history.pageCount || historyLoading} onClick={() => void loadHistory(history.page + 1)} type="button">{translate(language, 'common.next')}</button></div>}

              </section>
            )}

            {screen === 'capture' && (
              <section className="app-screen capture-screen"><div className="screen-heading"><div><p>{translate(language, 'capture.subtitle')}</p><h1>{translate(language, 'screen.captureTitle')}</h1><span>{selectedItem?.crop_name ?? '작물'} · {selectedItem?.cultivar_name ?? '품종 미지정'}</span></div></div><div className="module-tabs"><button className={effectiveFruitTab === 'video' ? 'selected' : ''} onClick={() => setFruitTab('video')} type="button">{translate(language, 'upload.video')}</button><button className={effectiveFruitTab === 'photo' ? 'selected' : ''} onClick={() => setFruitTab('photo')} type="button">{translate(language, 'upload.photo')}</button>{canViewRevenue && <button className={effectiveFruitTab === 'forecast' ? 'selected' : ''} onClick={() => setFruitTab('forecast')} type="button">예상 수익</button>}</div><div className="module-workspace">{!farmId || !selectedItem ? <div className="screen-empty"><span>!</span><strong>농장과 품목 연결이 필요합니다.</strong><p>계약 정보가 계정에 연결되면 기능을 사용할 수 있습니다.</p></div> : effectiveFruitTab === 'video' ? <><div className="workspace-heading"><span>{translate(language, 'capture.uploadOnce')}</span><h2>{translate(language, 'capture.combinedVideoTitle')}</h2><p>{translate(language, 'capture.combinedVideoDescription')}</p></div><div className="analysis-scope-grid"><article><b>{translate(language, 'capture.rgbRequired')}</b><span>{translate(language, 'capture.findFruitScenes')}</span><span>{translate(language, 'capture.ripenessAndGrade')}</span><span>{translate(language, 'alert.suspiciousLeaf')}</span></article><article><b>{translate(language, 'capture.thermalOptional')}</b><span>{translate(language, 'capture.thermalForMites')}</span><span>{translate(language, 'capture.leafTemperatureDifference')}</span><span>{translate(language, 'capture.matchFrames')}</span></article></div><VideoUploadForm farmId={farmId} itemId={selectedItem.id} language={language} onUploaded={() => reload()} /><p className="data-scope-note"><strong>{translate(language, 'capture.afterSubmit')}</strong> {translate(language, 'capture.afterSubmitDescription')}</p></> : effectiveFruitTab === 'photo' ? <div className="photo-analysis-stack"><section><div className="workspace-heading"><span>과실 사진</span><h2>익은 정도·품질 등급 판독</h2><p>현재는 설향 사진을 판독할 수 있습니다. 다른 품종은 충분한 사진과 판독 기준이 준비되면 사용할 수 있습니다.</p></div><CameraCapture enabled={selectedModelReady} farmId={farmId} cultivarCode={selectedItem.cultivar_code ?? ''} cultivarName={selectedItem.display_name} onUploaded={() => reload()} /></section><section><div className="workspace-heading"><span>잎 사진</span><h2>{pestText(language, 'photoTitle')}</h2><p>일반 잎 사진은 꼭 필요합니다. 같은 잎의 열화상 사진이 있으면 함께 올릴 수 있습니다.</p></div><PestCaptureForm defaultPestCode={pestCode || 'OTHER'} key={`${farmId}:${selectedItem.id}:${pestCode}`} farmId={farmId} itemId={selectedItem.id} language={language} onUploaded={() => reload()} /></section></div> : <><div className="workspace-heading"><span>영상 판독이 끝나면 자동으로 계산</span><h2>예상 수익 결과</h2><p>영상에 같은 딸기가 여러 번 보여도 한 개로 세고, 등급별 수량과 예상 시세를 합쳐 계산합니다. 농민이 값을 따로 입력할 필요가 없습니다.</p></div><RevenueForecast forecasts={selectedRevenueForecasts} itemName={selectedItem.display_name} jobs={selectedForecastJobs} /></>}</div><p className="capture-safety"><strong>결과 안내</strong> 판독 결과는 농장 운영을 돕기 위한 값입니다.{canViewRevenue && ' 실제 정산 등급·시세·수수료에 따라 예상 수익이 달라질 수 있습니다.'}</p></section>
            )}

            {screen === 'management' && (
              <section className="app-screen management-screen">
                <div className="screen-heading"><div><p>{translate(language, 'management.subtitle')}</p><h1>{translate(language, 'menu.management')}</h1><span>{data.selectedFarm?.name ?? '농장 연결 대기'}</span></div></div>
                <div className="module-tabs"><button aria-pressed={managementTab === 'overview'} className={managementTab === 'overview' ? 'selected' : ''} onClick={() => setManagementTab('overview')} type="button">{pestText(language, 'overview')}</button><button aria-pressed={managementTab === 'harvest'} className={managementTab === 'harvest' ? 'selected' : ''} onClick={() => setManagementTab('harvest')} type="button">{translate(language, 'history.harvest')}</button></div>
                {!farmId ? <div className="module-workspace screen-empty"><strong>농장 연결이 필요합니다.</strong></div> : managementTab === 'harvest' ? selectedItem ? <HarvestLog farmId={farmId} itemId={selectedItem.id} itemName={selectedItem.display_name} key={`${farmId}:${selectedItem.id}`} language={language} /> : <div className="screen-empty"><strong>농장과 품목 연결이 필요합니다.</strong></div> : <>
                  <FarmStatus farmId={farmId} items={data.items} language={language} />
                  <div className="management-quick-actions">
                    <button onClick={openChat} type="button"><span aria-hidden="true">•••</span><div><strong>{translate(language, 'chat.open')}</strong><small>{translate(language, 'chat.managementHelp')}</small></div></button>
                    <button onClick={() => open('account')} type="button"><span aria-hidden="true">◎</span><div><strong>{translate(language, 'account.title')}</strong><small>{translate(language, 'management.accountHelp')}</small></div></button>
                  </div>
                  {data.account.permissions.manageMembers ? <>
                    <div className="management-section-heading member-heading"><div><span>{translate(language, 'management.members')}</span><h2>{translate(language, 'management.membersTitle')}</h2></div></div>
                    <AccountCenter account={data.account} farmId={farmId} key={`${farmId}:${data.account.displayName ?? ''}`} language={language} mode="members" onChanged={() => reload()} />
                  </> : <div className="module-workspace management-readonly"><div className="workspace-heading"><span>{translate(language, 'management.workerLabel')}</span><h2>{translate(language, 'management.workerTitle')}</h2><p>{translate(language, 'management.workerDesc')}</p></div><p className="data-scope-note"><strong>{translate(language, 'alert.sharedNotes')}</strong> {recordText(language, 'commentsHelp')}</p></div>}
                </>}
              </section>
            )}

            {screen === 'account' && (
              <section className="app-screen account-screen">
                <div className="screen-heading"><div><p>내 정보와 알림</p><h1>{translate(language, 'account.title')}</h1><span>{data.selectedFarm?.name ?? '농장 연결 대기'} · {accountRoleName}</span></div></div>
                {farmId ? <AccountCenter account={data.account} farmId={farmId} key={`${farmId}:${data.account.displayName ?? ''}:${data.account.phone ?? ''}`} language={language} onChanged={() => reload()} /> : <div className="module-workspace screen-empty"><strong>계약 농장 연결을 기다리고 있습니다.</strong><p>농장 정보가 계정에 연결되면 사용자와 알림 설정을 관리할 수 있습니다.</p></div>}
              </section>
            )}
        </>
      </div>
      {farmId && <FarmMiniChat farmId={farmId} farmName={data.selectedFarm?.name ?? translate(language, 'common.farm')} key={farmId} language={language} onOpenChange={setChatOpen} open={chatOpen} />}
      <nav aria-label={translate(language, 'common.pageMove')} className="page-jump-buttons">
        <button aria-label={translate(language, 'common.toTop')} disabled={pageEdge.top} onClick={() => scrollPage('top')} title={translate(language, 'common.toTop')} type="button"><span aria-hidden="true">↑</span><b>{translate(language, 'common.toTopShort')}</b></button>
        <button aria-label={translate(language, 'common.toBottom')} disabled={pageEdge.bottom} onClick={() => scrollPage('bottom')} title={translate(language, 'common.toBottom')} type="button"><span aria-hidden="true">↓</span><b>{translate(language, 'common.toBottomShort')}</b></button>
      </nav>
      {navigation(true)}
    </main>
  );
}
