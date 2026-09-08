'use client';

import { useEffect, useState } from 'react';
import { localeForLanguage, translate, type Language } from '@/app/lib/i18n';

type HarvestRun = {
  id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  started_by_name_snapshot: string | null;
  completed_by_name_snapshot: string | null;
  note: string;
  harvested_count: number;
  total_weight_g: number;
  item_name: string;
};

function dateKey(daysAgo = 0) {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function dateTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function timeOnly(value: string | null, language: Language) {
  if (!value) return translate(language, 'harvest.working');
  return new Intl.DateTimeFormat(localeForLanguage(language), { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}

function duration(startedAt: string, completedAt: string | null, language: Language) {
  const end = completedAt ? new Date(completedAt).getTime() : Date.now();
  const minutes = Math.max(0, Math.round((end - new Date(startedAt).getTime()) / 60_000));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours > 0
    ? `${hours}${translate(language, 'harvest.hour')} ${rest}${translate(language, 'harvest.minute')}`
    : `${rest}${translate(language, 'harvest.minute')}`;
}

function visibleSnapshotName(value: string | null, language: Language) {
  const name = value?.trim() ?? '';
  return name && !name.includes('@') ? name : translate(language, 'role.worker');
}

export function HarvestLog({ farmId, itemId, itemName, language }: {
  farmId: string;
  itemId: string;
  itemName: string;
  language: Language;
}) {
  const [from, setFrom] = useState(() => dateKey(30));
  const [to, setTo] = useState(() => dateKey());
  const [rows, setRows] = useState<HarvestRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    if (!farmId || !itemId) return;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ farmId, itemId, from, to });
      const response = await fetch(`/api/harvest-runs?${params}`, { cache: 'no-store' });
      const result = await response.json() as { rows?: HarvestRun[]; error?: string };
      if (!response.ok) throw new Error(translate(language, 'harvest.loadFailed'));
      setRows(result.rows ?? []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'harvest.loadFailed'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
    // item change is the automatic refresh boundary; date searches use the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farmId, itemId]);

  return (
    <div className="harvest-log">
      <section className="harvest-clock-card device-pending">
        <div>
          <span>{itemName} · {translate(language, 'harvest.today')}</span>
          <h2>{translate(language, 'harvest.devicePending')}</h2>
          <p>{translate(language, 'harvest.devicePendingDesc')}</p>
        </div>
        <strong className="harvest-device-status">{translate(language, 'harvest.autoRecordLater')}</strong>
      </section>
      {error && <div className="review-feedback error" role="alert">{error}</div>}
      <form className="harvest-date-filter" onSubmit={(event) => { event.preventDefault(); void load(); }}>
        <label><span>{translate(language, 'harvest.startDate')}</span><input max={to} onChange={(event) => setFrom(event.target.value)} type="date" value={from} /></label>
        <label><span>{translate(language, 'harvest.endDate')}</span><input min={from} onChange={(event) => setTo(event.target.value)} type="date" value={to} /></label>
        <button disabled={loading} type="submit">{loading ? translate(language, 'common.loading') : translate(language, 'harvest.byDate')}</button>
      </form>
      <div className="harvest-run-list">
        {loading ? <div className="screen-empty compact"><strong>{translate(language, 'common.loading')}</strong></div> : rows.length === 0 ? <div className="screen-empty compact"><strong>{translate(language, 'harvest.noRows')}</strong><p>{translate(language, 'harvest.emptyHelp')}</p></div> : rows.map((row) => (
          <article key={row.id}>
            <span className={row.status === 'IN_PROGRESS' ? 'running' : ''}>{row.status === 'IN_PROGRESS' ? translate(language, 'harvest.working') : translate(language, 'harvest.completed')}</span>
            <div><strong>{dateTime(row.started_at, language)}</strong><p>{visibleSnapshotName(row.started_by_name_snapshot, language)} {translate(language, 'harvest.started')}{row.completed_by_name_snapshot ? ` · ${visibleSnapshotName(row.completed_by_name_snapshot, language)} ${translate(language, 'harvest.ended')}` : ''}</p>{row.note && <small>{translate(language, 'harvest.note')}: {row.note}</small>}</div>
            <div className="harvest-time"><span>{timeOnly(row.started_at, language)} → {timeOnly(row.completed_at, language)}</span><b>{duration(row.started_at, row.completed_at, language)}</b></div>
            <div className="harvest-count"><span>{translate(language, 'harvest.count')}</span><strong>{row.harvested_count.toLocaleString(localeForLanguage(language))}{translate(language, 'harvest.pieces')}</strong></div>
          </article>
        ))}
      </div>
    </div>
  );
}
