'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { localeForLanguage, type Language } from '@/app/lib/i18n';
import './notification-center.css';
import { notificationLoadState } from './notification-load-state';

type NotificationRow = {
  recipient_id: string;
  notification_id: string;
  category: string;
  notification_type: string;
  severity: string;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  location_state_id: string | null;
  case_id: string | null;
  deep_link_screen: string | null;
  payload_json: string;
  created_at: string;
  read_at: string | null;
};

type ResponseShape = { rows: NotificationRow[]; unreadCount: number; error?: string };

const copy: Record<Language, {
  label: string; title: string; empty: string; markAll: string; dismiss: string; loadError: string;
}> = {
  ko: { label: '알림', title: '알림', empty: '새로운 알림이 없습니다.', markAll: '모두 읽음', dismiss: '알림에서 지우기', loadError: '알림을 불러오지 못했습니다.' },
  vi: { label: 'Thông báo', title: 'Thông báo', empty: 'Không có thông báo mới.', markAll: 'Đánh dấu tất cả đã đọc', dismiss: 'Ẩn thông báo', loadError: 'Không tải được thông báo.' },
  th: { label: 'การแจ้งเตือน', title: 'การแจ้งเตือน', empty: 'ไม่มีการแจ้งเตือนใหม่', markAll: 'อ่านทั้งหมด', dismiss: 'ซ่อนการแจ้งเตือน', loadError: 'โหลดการแจ้งเตือนไม่สำเร็จ' },
  'zh-CN': { label: '通知', title: '通知', empty: '没有新的通知。', markAll: '全部已读', dismiss: '隐藏通知', loadError: '无法加载通知。' },
};

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}

export function NotificationCenter({ farmId, language, onOpenScouting }: {
  farmId: string;
  language: Language;
  onOpenScouting: (locationStateId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<{ farmId: string; rows: NotificationRow[]; unreadCount: number } | null>(null);
  const [loadStatus, setLoadStatus] = useState({ farmId: '', loading: false, error: '' });
  const [error, setError] = useState('');
  const requestId = useRef(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const text = copy[language];
  const current = snapshot?.farmId === farmId ? snapshot : null;
  const rows = current?.rows ?? [];
  const unreadCount = current?.unreadCount ?? 0;
  const loadError = loadStatus.farmId === farmId ? loadStatus.error : '';
  const loading = loadStatus.farmId === farmId && loadStatus.loading;
  const viewState = notificationLoadState({ loading, failed: Boolean(loadError), loaded: Boolean(current), rowCount: rows.length });
  const stateCopy = {
    ko: { loading: '알림을 불러오는 중입니다.', retry: '다시 시도', stale: '마지막으로 불러온 알림을 표시합니다.' },
    vi: { loading: 'Đang tải thông báo.', retry: 'Thử lại', stale: 'Đang hiển thị thông báo được tải gần nhất.' },
    th: { loading: 'กำลังโหลดการแจ้งเตือน', retry: 'ลองอีกครั้ง', stale: 'กำลังแสดงการแจ้งเตือนที่โหลดล่าสุด' },
    'zh-CN': { loading: '正在加载通知。', retry: '重试', stale: '当前显示最近一次加载的通知。' },
  }[language];

  const load = useCallback(async () => {
    const id = ++requestId.current;
    if (!farmId) { setSnapshot(null); return; }
    setLoadStatus({ farmId, loading: true, error: '' });
    try {
      const response = await fetch(`/api/notifications?farmId=${encodeURIComponent(farmId)}&limit=30`, { cache: 'no-store' });
      const result = await response.json() as ResponseShape;
      if (!response.ok) throw new Error(result.error ?? text.loadError);
      if (id !== requestId.current) return;
      setSnapshot({ farmId, rows: result.rows, unreadCount: result.unreadCount });
      setLoadStatus({ farmId, loading: false, error: '' });
      setError('');
    } catch (caught) {
      if (id === requestId.current) setLoadStatus({ farmId, loading: false, error: caught instanceof Error ? caught.message : text.loadError });
    }
  }, [farmId, text.loadError]);

  useEffect(() => {
    const handle = window.setTimeout(() => { void load(); }, 0);
    return () => { window.clearTimeout(handle); requestId.current += 1; };
  }, [load]);
  useEffect(() => {
    if (!open) return;
    const handle = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handle);
    return () => document.removeEventListener('mousedown', handle);
  }, [open]);

  async function update(action: 'READ' | 'DISMISS' | 'READ_ALL', notificationId?: string) {
    if (!farmId) return;
    const response = await fetch('/api/notifications', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ farmId, action, notificationId }),
    });
    if (!response.ok) {
      const result = await response.json() as { error?: string };
      setError(result.error ?? text.loadError);
      return;
    }
    await load();
  }

  async function openNotification(row: NotificationRow) {
    if (!row.read_at) await update('READ', row.notification_id);
    if (row.entity_type === 'SCOUTING_CASE' && row.location_state_id) {
      setOpen(false);
      onOpenScouting(row.location_state_id);
    }
  }

  return <div className="notification-center" ref={rootRef}>
    <button aria-expanded={open} aria-label={text.label} className="notification-bell" disabled={!farmId}
      onClick={() => { setOpen((current) => !current); if (!open) void load(); }} type="button">
      <span aria-hidden="true">🔔</span>
      {unreadCount > 0 && <b>{unreadCount > 99 ? '99+' : unreadCount}</b>}
    </button>
    {open && farmId && <section aria-label={text.title} aria-busy={viewState === 'LOADING'} className="notification-panel">
      <header><strong>{text.title}</strong>{unreadCount > 0 && <button onClick={() => void update('READ_ALL')} type="button">{text.markAll}</button>}</header>
      {error && <p className="notification-error" role="alert">{error}</p>}
      {loadError && <div className="notification-error" role="alert">{loadError}{viewState === 'STALE' && <p>{stateCopy.stale}</p>}<button disabled={loading} onClick={() => void load()} type="button">{stateCopy.retry}</button></div>}
      {viewState === 'LOADING' ? <div className="notification-empty" role="status">{stateCopy.loading}</div>
        : viewState === 'EMPTY' ? <div className="notification-empty">{text.empty}</div>
          : rows.length > 0 ? <div className="notification-list">
        {rows.map((row) => <article className={`${row.read_at ? 'read' : 'unread'} severity-${row.severity.toLowerCase()}`} key={row.recipient_id}>
          <button className="notification-open" onClick={() => void openNotification(row)} type="button">
            <span className="notification-dot" aria-hidden="true" />
            <div><strong>{row.title}</strong><p>{row.body}</p><time>{formatTime(row.created_at, language)}</time></div>
          </button>
          <button aria-label={text.dismiss} className="notification-dismiss" onClick={() => void update('DISMISS', row.notification_id)} title={text.dismiss} type="button">×</button>
        </article>)}
      </div> : null}
    </section>}
  </div>;
}
