'use client';

import { useState } from 'react';
import { localeForLanguage, translate, type Language } from '@/app/lib/i18n';
import { MiteRecordNotes } from './MiteRecordNotes';

export type MiteAlertRecord = {
  id: string;
  item_id: string | null;
  item_name: string | null;
  crop_name: string | null;
  cultivar_name: string | null;
  class_label: string;
  confidence: number | null;
  decision_status: string;
  created_at: string;
  house_name: string | null;
  bed_name: string | null;
  zone_name: string | null;
  review_verdict: string | null;
  review_quick_note_code: string | null;
  review_note: string | null;
  review_note_language: string | null;
  reviewer_name: string | null;
  reviewer_role: string | null;
  reviewed_at: string | null;
};

export type MiteAlertPagination = {
  status: 'OPEN' | 'DONE';
  page: number;
  limit: number;
  total: number;
  pageCount: number;
  openCount: number;
  doneCount: number;
};

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function roleName(value: string | null, language: Language) {
  return value === 'ADMIN' ? translate(language, 'role.admin')
    : value === 'OWNER' ? translate(language, 'role.owner')
      : value === 'WORKER' ? translate(language, 'role.worker') : '';
}

function visibleReviewerName(value: string | null, role: string | null, language: Language) {
  const name = value?.trim() ?? '';
  return name && !name.includes('@') ? name : roleName(role, language) || translate(language, 'role.worker');
}

function verdictName(value: string | null, language: Language) {
  if (value === 'MITE_CONFIRMED') return translate(language, 'alert.miteYes');
  if (value === 'NOT_MITE') return translate(language, 'alert.miteNo');
  if (value === 'RECHECK') return translate(language, 'alert.recheck');
  return translate(language, 'alert.notReviewed');
}

function quickNoteName(value: string | null, language: Language) {
  if (value === 'LEAF_BACK_CHECKED') return translate(language, 'alert.leafBackChecked');
  if (value === 'WEBBING_SEEN') return translate(language, 'alert.webbingSeen');
  if (value === 'LEAF_DAMAGE_ONLY') return translate(language, 'alert.leafDamageOnly');
  if (value === 'PHOTO_NEEDED') return translate(language, 'alert.photoNeeded');
  return '';
}

export function MiteAlertReview({
  alerts,
  farmId,
  canReview,
  language,
  pagination,
  onPageChange,
  onReviewed,
}: {
  alerts: MiteAlertRecord[];
  farmId: string;
  canReview: boolean;
  language: Language;
  pagination: MiteAlertPagination;
  onPageChange: (status: 'OPEN' | 'DONE', page: number) => void;
  onReviewed: () => void;
}) {
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [quickNotes, setQuickNotes] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const [sending, setSending] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const tab = pagination.status;
  const rows = alerts;
  const pageCount = Math.max(1, pagination.pageCount);
  const safePage = Math.min(pagination.page, pageCount);

  function selectTab(nextTab: 'OPEN' | 'DONE') {
    setEditing(null);
    onPageChange(nextTab, 1);
  }

  async function submit(alert: MiteAlertRecord, verdict: 'MITE_CONFIRMED' | 'NOT_MITE' | 'RECHECK') {
    setSending(alert.id);
    setMessage('');
    setError('');
    try {
      const response = await fetch('/api/alert-reviews', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          farmId,
          predictionId: alert.id,
          verdict,
          quickNoteCode: quickNotes[alert.id] ?? '',
          note: notes[alert.id] ?? '',
          noteLanguage: language,
        }),
      });
      await response.json();
      if (!response.ok) throw new Error(translate(language, 'alert.reviewSaveFailed'));
      setMessage(translate(language, 'alert.reviewSaved'));
      setEditing(null);
      setNotes((current) => ({ ...current, [alert.id]: '' }));
      setQuickNotes((current) => ({ ...current, [alert.id]: '' }));
      onReviewed();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'alert.reviewSaveFailed'));
    } finally {
      setSending(null);
    }
  }

  return (
    <section className="alert-review-board">
      <header className="alert-review-heading">
        <div>
          <span>{translate(language, 'alert.suspectIntro')}</span>
          <h2>{translate(language, 'alert.title')}</h2>
          <p>{translate(language, 'alert.explanation')}</p>
        </div>
        <div className="alert-review-tabs" role="tablist" aria-label="응애 알림 구분">
          <button aria-selected={tab === 'OPEN'} className={tab === 'OPEN' ? 'selected' : ''} onClick={() => selectTab('OPEN')} role="tab" type="button">{translate(language, 'alert.open')} <b>{pagination.openCount}</b></button>
          <button aria-selected={tab === 'DONE'} className={tab === 'DONE' ? 'selected' : ''} onClick={() => selectTab('DONE')} role="tab" type="button">{translate(language, 'alert.done')} <b>{pagination.doneCount}</b></button>
        </div>
      </header>
      {message && <div className="review-feedback success" role="status">{message}</div>}
      {error && <div className="review-feedback error" role="alert">{error}</div>}
      {rows.length === 0 ? (
        <div className="screen-empty compact">
          <strong>{tab === 'OPEN' ? translate(language, 'alert.noOpen') : translate(language, 'alert.noDone')}</strong>
          <p>{translate(language, 'alert.emptyDesc')}</p>
        </div>
      ) : (
        <div className="alert-review-list">
          {rows.map((alert) => {
            const location = [alert.house_name, alert.bed_name, alert.zone_name].filter(Boolean).join(' · ') || translate(language, 'alert.locationRequired');
            const itemName = alert.item_name || [alert.crop_name, alert.cultivar_name].filter(Boolean).join(' · ') || translate(language, 'management.notSet');
            const showForm = editing === alert.id;
            return (
              <article className="alert-review-item" key={alert.id}>
                <div className="alert-review-summary">
                  <span className={`review-verdict ${alert.review_verdict?.toLowerCase() ?? 'open'}`}>{verdictName(alert.review_verdict, language)}</span>
                  <div>
                    <strong>{itemName} · {location}</strong>
                    <p>{formatTime(alert.created_at, language)} · {translate(language, 'alert.suspected')}</p>
                  </div>
                  {alert.confidence !== null && <b>{translate(language, 'alert.confidence', { percent: Math.round(alert.confidence * 100) })}</b>}
                </div>
                {alert.reviewed_at && (
                  <div className="review-history-line">
                    <strong>{visibleReviewerName(alert.reviewer_name, alert.reviewer_role, language)}</strong>
                    <span>{roleName(alert.reviewer_role, language)} · {formatTime(alert.reviewed_at, language)}</span>
                    {alert.review_quick_note_code && <p>{quickNoteName(alert.review_quick_note_code, language)}</p>}
                    {alert.review_note && <p>{translate(language, 'alert.note')}: {alert.review_note}</p>}
                  </div>
                )}
                {showForm && canReview ? (
                  <div className="alert-review-form">
                    <label>
                      <span>{translate(language, 'alert.quickNote')}</span>
                      <select onChange={(event) => setQuickNotes((current) => ({ ...current, [alert.id]: event.target.value }))} value={quickNotes[alert.id] ?? ''}>
                        <option value="">{translate(language, 'alert.quickNone')}</option>
                        <option value="LEAF_BACK_CHECKED">{translate(language, 'alert.leafBackChecked')}</option>
                        <option value="WEBBING_SEEN">{translate(language, 'alert.webbingSeen')}</option>
                        <option value="LEAF_DAMAGE_ONLY">{translate(language, 'alert.leafDamageOnly')}</option>
                        <option value="PHOTO_NEEDED">{translate(language, 'alert.photoNeeded')}</option>
                      </select>
                    </label>
                    <label>
                      <span>{translate(language, 'alert.note')} <small>{translate(language, 'common.optional')}</small></span>
                      <textarea maxLength={300} onChange={(event) => setNotes((current) => ({ ...current, [alert.id]: event.target.value }))} placeholder={translate(language, 'alert.notePlaceholder')} rows={2} value={notes[alert.id] ?? ''} />
                    </label>
                    <div>
                      <button className="confirm-mite" disabled={sending === alert.id} onClick={() => void submit(alert, 'MITE_CONFIRMED')} type="button">{translate(language, 'alert.miteYes')}</button>
                      <button className="not-mite" disabled={sending === alert.id} onClick={() => void submit(alert, 'NOT_MITE')} type="button">{translate(language, 'alert.miteNo')}</button>
                      <button className="recheck" disabled={sending === alert.id} onClick={() => void submit(alert, 'RECHECK')} type="button">{translate(language, 'alert.recheck')}</button>
                    </div>
                  </div>
                ) : canReview ? (
                  <button className="review-again" onClick={() => setEditing(alert.id)} type="button">{translate(language, tab === 'OPEN' ? 'alert.reviewNow' : 'alert.reviewAgain')}</button>
                ) : null}
                <MiteRecordNotes canWrite={canReview} farmId={farmId} language={language} predictionId={alert.id} />
              </article>
            );
          })}
        </div>
      )}
      {pagination.pageCount > 1 && <div className="history-pagination alert-pagination"><button disabled={safePage <= 1} onClick={() => { onPageChange(tab, safePage - 1); setEditing(null); }} type="button">{translate(language, 'common.previous')}</button><span>{safePage} / {pageCount}</span><button disabled={safePage >= pageCount} onClick={() => { onPageChange(tab, safePage + 1); setEditing(null); }} type="button">{translate(language, 'common.next')}</button></div>}
    </section>
  );
}
