'use client';

/* eslint-disable @next/next/no-img-element */

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { languageNames, localeForLanguage, translate, type Language } from '@/app/lib/i18n';

type RecordNote = {
  id: string;
  parent_note_id: string | null;
  author_name_snapshot: string;
  author_role_snapshot: string;
  author_account_snapshot: string;
  language: Language;
  content: string;
  translated_content: string | null;
  detected_source_language: string | null;
  translation_source_updated_at: string | null;
  display_content: string;
  display_language: Language;
  translation_status: 'original' | 'translated' | 'unavailable';
  created_at: string;
  updated_at: string;
  is_mine: boolean;
  can_edit: boolean;
  can_delete: boolean;
};

type ShareTargetContext = {
  timestamp_ms: number;
  house_code: string | null;
  house_name: string | null;
  bed_code: string | null;
  bed_name: string | null;
  zone_code: string | null;
  zone_name: string | null;
  video_modality: string | null;
  location_source: string;
};

type CheckpointFrame = ShareTargetContext & {
  prediction_id: string;
  frame_id: string;
  frame_index: number;
  class_label: string;
  confidence: number | null;
  note_count: number;
};

type OnDeviceTranslator = {
  translate: (text: string) => Promise<string>;
  destroy?: () => void;
};

type OnDeviceTranslatorFactory = {
  availability: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<string | null>;
  create: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<OnDeviceTranslator>;
};

type TranslationState = 'idle' | 'working' | 'ready' | 'partial' | 'unavailable';

type SharedTranslation = {
  content: string;
  detectedSourceLanguage: string | null;
  sourceUpdatedAt: string;
};

const FRAME_PAGE_SIZE = 8;

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function videoTime(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function roleName(value: string, language: Language) {
  return value === 'ADMIN' ? translate(language, 'role.admin')
    : value === 'OWNER' ? translate(language, 'role.owner')
      : translate(language, 'role.worker');
}

function roleClass(value: string) {
  return value === 'ADMIN' ? 'role-admin' : value === 'OWNER' ? 'role-owner' : 'role-worker';
}

function browserLanguage(value: Language) {
  return value === 'zh-CN' ? 'zh' : value;
}

function visibleAuthorName(note: Pick<RecordNote, 'author_name_snapshot' | 'author_account_snapshot'>) {
  const name = note.author_name_snapshot.trim();
  return name && !name.includes('@') ? name : note.author_account_snapshot;
}

function normalizedLanguage(value: string | null | undefined) {
  const normalized = value?.trim().toLowerCase();
  if (normalized === 'zh' || normalized === 'zh-cn') return 'zh-CN';
  if (normalized === 'ko' || normalized === 'vi' || normalized === 'th') return normalized;
  return null;
}

function onDeviceTranslatorFactory() {
  return (globalThis as typeof globalThis & { Translator?: OnDeviceTranslatorFactory }).Translator;
}

function locationName(frame: ShareTargetContext, language: Language) {
  const parts = [frame.house_name || frame.house_code, frame.bed_name || frame.bed_code, frame.zone_name || frame.zone_code]
    .filter((value): value is string => Boolean(value?.trim()));
  return parts.length ? parts.join(' · ') : translate(language, 'alert.locationUnknown');
}

function shortShareValue(value: string | null | undefined, max = 32) {
  const normalized = value?.replace(/\s+/g, ' ').trim() ?? '';
  return Array.from(normalized).slice(0, max).join('');
}

function shareLocation(frame: ShareTargetContext, language: Language) {
  const house = shortShareValue(frame.house_name || frame.house_code);
  const zone = shortShareValue(frame.zone_name || frame.zone_code);
  const bed = shortShareValue(frame.bed_name || frame.bed_code);
  return [
    house && `${translate(language, 'chat.forwardHouse')}: ${house}`,
    zone && `${translate(language, 'chat.forwardZone')}: ${zone}`,
    bed && `${translate(language, 'chat.forwardBed')}: ${bed}`,
  ]
    .filter(Boolean)
    .join(' · ') || translate(language, 'chat.forwardUnknownLocation');
}

function shareVideoLabel(modality: string | null | undefined, language: Language) {
  if (modality === 'DUAL_SENSOR_VIDEO') return translate(language, 'chat.forwardDualVideo');
  if (modality === 'THERMAL_VIDEO') return translate(language, 'chat.forwardThermalVideo');
  if (modality === 'RGB_VIDEO') return translate(language, 'chat.forwardRgbVideo');
  return translate(language, 'chat.forwardDefaultVideo');
}

function farmChatText(frame: ShareTargetContext, note: string, language: Language) {
  const compactNote = note.replace(/\s+/g, ' ').trim();
  const shortenedNote = `${Array.from(compactNote).slice(0, 220).join('')}${Array.from(compactNote).length > 220 ? '…' : ''}`;
  return [
    translate(language, 'chat.forwardMiteTitle'),
    `${translate(language, 'chat.forwardLocation')}: ${shareLocation(frame, language)}`,
    `${translate(language, 'chat.forwardVideo')}: ${shareVideoLabel(frame.video_modality, language)} · ${videoTime(frame.timestamp_ms)}`,
    `${translate(language, 'chat.forwardOpinion')}: ${shortenedNote}`,
  ].join('\n');
}

function sourceLanguageName(note: RecordNote) {
  const detected = normalizedLanguage(note.detected_source_language);
  return detected ? languageNames[detected] : languageNames[note.language] ?? note.language;
}

export function MiteRecordNotes({
  farmId,
  predictionId,
  sessionId,
  frameMode = false,
  canWrite,
  language,
}: {
  farmId: string;
  predictionId?: string;
  sessionId?: string;
  frameMode?: boolean;
  canWrite: boolean;
  language: Language;
}) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [framesLoaded, setFramesLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [rows, setRows] = useState<RecordNote[]>([]);
  const [frames, setFrames] = useState<CheckpointFrame[]>([]);
  const [targetContext, setTargetContext] = useState<ShareTargetContext | null>(null);
  const [framePage, setFramePage] = useState(1);
  const [selectedPredictionId, setSelectedPredictionId] = useState(predictionId ?? '');
  const [content, setContent] = useState('');
  const [editingId, setEditingId] = useState('');
  const [replyingTo, setReplyingTo] = useState<RecordNote | null>(null);
  const [shareWithFarmChat, setShareWithFarmChat] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [missingEvidence, setMissingEvidence] = useState<Record<string, boolean>>({});
  const [translationState, setTranslationState] = useState<TranslationState>('idle');
  const [showOriginalIds, setShowOriginalIds] = useState<Set<string>>(new Set());
  const loadSequence = useRef(0);
  const previousLanguage = useRef(language);

  const activePredictionId = predictionId || selectedPredictionId;
  const selectedFrame = frames.find((frame) => frame.prediction_id === activePredictionId) ?? null;
  const activeShareContext = selectedFrame ?? targetContext;
  const noteCount = frameMode ? frames.reduce((sum, frame) => sum + Number(frame.note_count || 0), 0) : rows.length;
  const framePageCount = Math.max(1, Math.ceil(frames.length / FRAME_PAGE_SIZE));
  const visibleFrames = frames.slice((framePage - 1) * FRAME_PAGE_SIZE, framePage * FRAME_PAGE_SIZE);
  const threadedRows = useMemo(() => {
    const ids = new Set(rows.map((note) => note.id));
    const roots = rows.filter((note) => !note.parent_note_id || !ids.has(note.parent_note_id));
    return roots.flatMap((root) => [root, ...rows.filter((note) => note.parent_note_id === root.id)]);
  }, [rows]);
  function evidenceUrl(modality: 'rgb' | 'thermal', targetPredictionId = activePredictionId) {
    const params = new URLSearchParams({ farmId, modality });
    if (targetPredictionId) params.set('predictionId', targetPredictionId);
    else if (sessionId) params.set('sessionId', sessionId);
    return `/api/mite-evidence?${params}`;
  }

  async function loadNotes(targetPredictionId = activePredictionId) {
    const sequence = ++loadSequence.current;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ farmId });
      params.set('language', language);
      if (targetPredictionId) params.set('predictionId', targetPredictionId);
      else if (sessionId) params.set('sessionId', sessionId);
      const response = await fetch(`/api/mite-record-notes?${params}`, { cache: 'no-store' });
      const result = await response.json() as {
        rows?: RecordNote[];
        targetContext?: ShareTargetContext | null;
        error?: string;
      };
      if (!response.ok) throw new Error(translate(language, 'alert.sharedNoteLoadFailed'));
      if (sequence !== loadSequence.current) return;
      setTargetContext(result.targetContext ?? null);
      const nextRows = result.rows ?? [];
      setRows(nextRows);
      setShowOriginalIds(new Set());
      if (targetPredictionId) {
        setFrames((current) => current.map((frame) => frame.prediction_id === targetPredictionId
          ? { ...frame, note_count: nextRows.length }
          : frame));
      }
      setLoaded(true);
      if (nextRows.some((note) => !note.translated_content)) {
        void translateMissingNotes(nextRows, targetPredictionId, sequence);
      } else {
        setTranslationState('ready');
      }
    } catch (caught) {
      if (sequence !== loadSequence.current) return;
      setError(caught instanceof Error ? caught.message : translate(language, 'alert.sharedNoteLoadFailed'));
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }

  async function requestSharedTranslations(notes: RecordNote[], targetPredictionId: string) {
    const batches: RecordNote[][] = [];
    let batch: RecordNote[] = [];
    let batchCharacters = 0;
    for (const note of notes) {
      if (batch.length >= 20 || batchCharacters + note.content.length > 6000) {
        batches.push(batch);
        batch = [];
        batchCharacters = 0;
      }
      batch.push(note);
      batchCharacters += note.content.length;
    }
    if (batch.length) batches.push(batch);

    const collected = new Map<string, SharedTranslation>();
    for (const notesBatch of batches) {
      try {
        const response = await fetch('/api/mite-record-notes', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            action: 'TRANSLATE_NOTES',
            farmId,
            predictionId: targetPredictionId || undefined,
            sessionId: targetPredictionId ? undefined : sessionId,
            noteIds: notesBatch.map((note) => note.id),
            targetLanguage: language,
          }),
        });
        const result = await response.json() as {
          translationUnavailable?: boolean;
          translations?: Array<{
            note_id: string;
            translated_content: string;
            detected_source_language: string | null;
            source_updated_at: string;
          }>;
        };
        if (result.translationUnavailable) break;
        if (!response.ok) continue;
        for (const translation of result.translations ?? []) {
          if (!translation.translated_content.trim()) continue;
          collected.set(translation.note_id, {
            content: translation.translated_content,
            detectedSourceLanguage: translation.detected_source_language,
            sourceUpdatedAt: translation.source_updated_at,
          });
        }
      } catch {
        // Missing shared translations can still use the private device fallback.
      }
    }
    return collected;
  }

  async function translateMissingNotes(sourceRows = rows, targetPredictionId = activePredictionId, sequence = loadSequence.current) {
    const pending = sourceRows.filter((note) => !note.translated_content);
    if (!pending.length) {
      setTranslationState('ready');
      return;
    }
    setTranslationState('working');
    const translated = await requestSharedTranslations(pending, targetPredictionId);
    if (sequence !== loadSequence.current) return;
    const stillPending = pending.filter((note) => translated.get(note.id)?.sourceUpdatedAt !== note.updated_at);
    const devicePending = stillPending.filter((note) => note.language !== language);
    const factory = devicePending.length ? onDeviceTranslatorFactory() : null;
    const groups = new Map<string, RecordNote[]>();
    for (const note of devicePending) {
      const sourceLanguage = browserLanguage(note.language);
      groups.set(sourceLanguage, [...(groups.get(sourceLanguage) ?? []), note]);
    }
    if (factory) for (const [sourceLanguage, notes] of groups) {
      let translator: OnDeviceTranslator | null = null;
      try {
        const options = { sourceLanguage, targetLanguage: browserLanguage(language) };
        const availability = await factory.availability(options);
        if (!availability || availability === 'unavailable') continue;
        translator = await factory.create(options);
        for (const note of notes) {
          const nextContent = (await translator.translate(note.content)).trim();
          if (!nextContent) continue;
          translated.set(note.id, {
            content: nextContent,
            detectedSourceLanguage: note.language,
            sourceUpdatedAt: note.updated_at,
          });
        }
      } catch {
        // Unsupported language pairs remain in their original language.
      } finally {
        translator?.destroy?.();
      }
    }
    if (sequence !== loadSequence.current) return;
    if (translated.size) {
      setRows((current) => current.map((note) => {
        const translation = translated.get(note.id);
        if (!translation || translation.sourceUpdatedAt !== note.updated_at) return note;
        const isOriginalLanguage = normalizedLanguage(translation.detectedSourceLanguage) === language;
        return {
          ...note,
          translated_content: translation.content,
          detected_source_language: translation.detectedSourceLanguage,
          translation_source_updated_at: translation.sourceUpdatedAt,
          display_content: isOriginalLanguage ? note.content : translation.content,
          display_language: language,
          translation_status: isOriginalLanguage ? 'original' : 'translated',
        };
      }));
    }
    const unresolved = pending.filter((note) => (
      translated.get(note.id)?.sourceUpdatedAt !== note.updated_at && note.language !== language
    ));
    setTranslationState(unresolved.length === 0 ? 'ready' : translated.size ? 'partial' : 'unavailable');
  }

  useEffect(() => {
    if (previousLanguage.current === language) return;
    previousLanguage.current = language;
    loadSequence.current += 1;
    const nextLanguage = language;
    queueMicrotask(() => {
      if (previousLanguage.current !== nextLanguage) return;
      setShowOriginalIds(new Set());
      setTranslationState('idle');
      if (!open) {
        setLoaded(false);
        setLoading(false);
        return;
      }
      setRows([]);
      setLoaded(false);
      if (activePredictionId) void loadNotes(activePredictionId);
      else if (frameMode && sessionId && !predictionId) void loadFrames();
      else void loadNotes(predictionId);
    });
  }, [language]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadFrames() {
    if (!sessionId) return;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ farmId, sessionId, mode: 'frames' });
      const response = await fetch(`/api/mite-record-notes?${params}`, { cache: 'no-store' });
      const result = await response.json() as { frames?: CheckpointFrame[]; error?: string };
      if (!response.ok) throw new Error(translate(language, 'alert.sharedNoteLoadFailed'));
      const nextFrames = result.frames ?? [];
      setFrames(nextFrames);
      setFramesLoaded(true);
      const nextPredictionId = nextFrames.some((frame) => frame.prediction_id === selectedPredictionId)
        ? selectedPredictionId
        : nextFrames[0]?.prediction_id ?? '';
      setSelectedPredictionId(nextPredictionId);
      const selectedIndex = Math.max(0, nextFrames.findIndex((frame) => frame.prediction_id === nextPredictionId));
      setFramePage(Math.floor(selectedIndex / FRAME_PAGE_SIZE) + 1);
      setMissingEvidence({});
      if (nextPredictionId) await loadNotes(nextPredictionId);
      else {
        setRows([]);
        setLoaded(true);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'alert.sharedNoteLoadFailed'));
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (!next) {
      setShareWithFarmChat(false);
      return;
    }
    if (frameMode && sessionId && !predictionId) void loadFrames();
    else void loadNotes(predictionId);
  }

  function chooseFrame(frame: CheckpointFrame) {
    setSelectedPredictionId(frame.prediction_id);
    setRows([]);
    setTargetContext(null);
    setLoaded(false);
    setEditingId('');
    setReplyingTo(null);
    setContent('');
    setShareWithFarmChat(false);
    setMessage('');
    setMissingEvidence({});
    void loadNotes(frame.prediction_id);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!content.trim() || (frameMode && !activePredictionId)) return;
    setSending(true);
    setError('');
    setMessage('');
    const wasEditing = Boolean(editingId);
    const savedContent = content.trim();
    const shouldShareWithFarmChat = shareWithFarmChat && !wasEditing && Boolean(activeShareContext);
    let farmChatDelivered: boolean | null = null;
    try {
      const response = await fetch('/api/mite-record-notes', {
        method: editingId ? 'PATCH' : 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          farmId,
          predictionId: activePredictionId || undefined,
          sessionId: activePredictionId ? undefined : sessionId,
          noteId: editingId || undefined,
          parentNoteId: editingId ? undefined : replyingTo?.id,
          content,
          languageHint: language,
        }),
      });
      await response.json();
      if (!response.ok) throw new Error(translate(language, 'alert.sharedNoteSaveFailed'));
      if (shouldShareWithFarmChat && activeShareContext) {
        try {
          const chatResponse = await fetch('/api/farm-chat-messages', {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({
              farmId,
              content: farmChatText(activeShareContext, savedContent, language),
              languageHint: language,
            }),
          });
          farmChatDelivered = chatResponse.ok;
        } catch {
          farmChatDelivered = false;
        }
      }
      setContent('');
      setEditingId('');
      setReplyingTo(null);
      setShareWithFarmChat(false);
      await loadNotes(activePredictionId);
      setMessage(farmChatDelivered === true
        ? translate(language, 'chat.shareMiteSuccess')
        : translate(language, wasEditing ? 'alert.sharedNoteUpdated' : 'alert.sharedNoteSaved'));
      if (farmChatDelivered === false) {
        setError(translate(language, 'chat.shareMitePartial'));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'alert.sharedNoteSaveFailed'));
    } finally {
      setSending(false);
    }
  }

  async function remove(note: RecordNote) {
    if (!window.confirm(translate(language, 'alert.sharedNoteDeleteConfirm'))) return;
    setSending(true);
    setError('');
    try {
      const params = new URLSearchParams({ farmId, noteId: note.id });
      if (activePredictionId) params.set('predictionId', activePredictionId);
      else if (sessionId) params.set('sessionId', sessionId);
      const response = await fetch(`/api/mite-record-notes?${params}`, { method: 'DELETE' });
      await response.json();
      if (!response.ok) throw new Error(translate(language, 'alert.sharedNoteSaveFailed'));
      if (editingId === note.id) setEditingId('');
      if (replyingTo?.id === note.id) setReplyingTo(null);
      setContent('');
      setMessage(translate(language, 'alert.sharedNoteDeleted'));
      await loadNotes(activePredictionId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'alert.sharedNoteSaveFailed'));
    } finally {
      setSending(false);
    }
  }

  const canCompose = canWrite && (!frameMode || Boolean(activePredictionId));

  return (
    <section className="record-notes">
      <button aria-expanded={open} className="record-notes-toggle" onClick={toggle} type="button">
        <span>{translate(language, frameMode ? 'alert.frameDiscussions' : 'alert.sharedNotes')}</span>
        <b>{(frameMode ? framesLoaded : loaded) ? noteCount : ''}</b>
        <i>{translate(language, open ? 'alert.hideSharedNotes' : 'alert.showSharedNotes')}</i>
      </button>
      {open && (
        <div className="record-notes-panel">
          {frameMode && framesLoaded && frames.length > 0 && (
            <div className="record-frame-picker">
              <header><strong>{translate(language, 'alert.problemScenes', { count: frames.length })}</strong><span>{translate(language, 'alert.sharedComments', { count: noteCount })}</span></header>
              <div className="record-frame-list">
                {visibleFrames.map((frame, index) => (
                  <button aria-current={frame.prediction_id === activePredictionId ? 'true' : undefined} aria-pressed={frame.prediction_id === activePredictionId} className={frame.prediction_id === activePredictionId ? 'selected' : ''} key={frame.frame_id} onClick={() => chooseFrame(frame)} type="button">
                    <span className="record-frame-index" aria-hidden="true">{String((framePage - 1) * FRAME_PAGE_SIZE + index + 1).padStart(2, '0')}</span>
                    <span className="record-frame-main"><strong>{locationName(frame, language)}</strong><small>{translate(language, 'alert.videoReference', { time: videoTime(frame.timestamp_ms) })}</small></span>
                    <span className="record-frame-stats"><b>{translate(language, 'alert.confidence', { percent: Math.round((frame.confidence ?? 0) * 100) })}</b><small>{translate(language, 'alert.sharedComments', { count: frame.note_count })}</small></span>
                  </button>
                ))}
              </div>
              {framePageCount > 1 && <div className="record-frame-pagination"><button disabled={framePage <= 1} onClick={() => setFramePage((current) => Math.max(1, current - 1))} type="button">{translate(language, 'common.previous')}</button><span aria-live="polite">{framePage} / {framePageCount}</span><button disabled={framePage >= framePageCount} onClick={() => setFramePage((current) => Math.min(framePageCount, current + 1))} type="button">{translate(language, 'common.next')}</button></div>}
            </div>
          )}

          {frameMode && framesLoaded && frames.length === 0 ? (
            <div className="record-notes-empty"><strong>{translate(language, 'alert.noProblemScenes')}</strong><span>{translate(language, 'alert.noProblemScenesDesc')}</span></div>
          ) : (
            <>
              {selectedFrame && <div className="record-frame-context"><div><span>{translate(language, 'alert.checkLocation')}</span><strong>{locationName(selectedFrame, language)}</strong><small>{translate(language, selectedFrame.location_source === 'SESSION_DEFAULT' ? 'alert.sessionLocation' : 'alert.frameLocation')} · {translate(language, 'alert.videoReference', { time: videoTime(selectedFrame.timestamp_ms) })}</small></div><b>{translate(language, 'alert.confidence', { percent: Math.round((selectedFrame.confidence ?? 0) * 100) })}</b></div>}
              <div className="record-evidence">
                {!missingEvidence.rgb && <figure><img alt={translate(language, 'alert.rgbEvidence')} onError={() => setMissingEvidence((current) => ({ ...current, rgb: true }))} src={evidenceUrl('rgb')} /><figcaption>{translate(language, 'alert.rgbEvidence')}</figcaption></figure>}
                {!missingEvidence.thermal && <figure><img alt={translate(language, 'alert.thermalEvidence')} onError={() => setMissingEvidence((current) => ({ ...current, thermal: true }))} src={evidenceUrl('thermal')} /><figcaption>{translate(language, 'alert.thermalEvidence')}</figcaption></figure>}
              </div>
              {(translationState === 'partial' || translationState === 'unavailable') && <div className={`record-translation-status ${translationState}`} role="status"><strong>{translate(language, 'alert.translationPartial')}</strong><button onClick={() => void translateMissingNotes()} type="button">{translate(language, 'alert.translationRetry')}</button></div>}
              {loading && !loaded ? <div className="record-notes-empty">{translate(language, 'common.loading')}</div> : rows.length === 0 ? <div className="record-notes-empty">{translate(language, 'alert.noSharedNotes')}</div> : (
                <div className="record-notes-list">
                  {threadedRows.map((note) => (
                    <article className={`${roleClass(note.author_role_snapshot)} ${note.parent_note_id ? 'reply' : ''}`} key={note.id}>
                      <header>
                        <span aria-hidden="true" className="record-note-avatar">{visibleAuthorName(note).slice(0, 1).toUpperCase()}</span>
                        <div><strong>{visibleAuthorName(note)}</strong><span>{formatTime(note.updated_at, language)}</span></div>
                        <div className="record-note-badges"><b>{roleName(note.author_role_snapshot, language)}</b>{visibleAuthorName(note) !== note.author_account_snapshot && <span>{translate(language, 'alert.accountCode', { code: note.author_account_snapshot })}</span>}{note.is_mine && <em>{translate(language, 'alert.myAccount')}</em>}<small>{sourceLanguageName(note)}</small></div>
                      </header>
                      <p lang={browserLanguage(showOriginalIds.has(note.id) ? note.language : note.display_language)}>{showOriginalIds.has(note.id) ? note.content : note.display_content}</p>
                      {(canWrite || note.can_edit || note.can_delete || note.translation_status === 'translated') && <footer>{note.translation_status === 'translated' && <button onClick={() => setShowOriginalIds((current) => { const next = new Set(current); if (next.has(note.id)) next.delete(note.id); else next.add(note.id); return next; })} type="button">{translate(language, showOriginalIds.has(note.id) ? 'alert.showTranslation' : 'alert.showOriginal')}</button>}{canWrite && <button onClick={() => { setReplyingTo(note); setEditingId(''); setContent(''); setShareWithFarmChat(false); setMessage(''); }} type="button">{translate(language, 'alert.reply')}</button>}{note.can_edit && <button onClick={() => { setEditingId(note.id); setReplyingTo(null); setContent(note.content); setShareWithFarmChat(false); setMessage(''); }} type="button">{translate(language, 'notes.edit')}</button>}{note.can_delete && <button className="delete" disabled={sending} onClick={() => void remove(note)} type="button">{translate(language, 'notes.delete')}</button>}</footer>}
                    </article>
                  ))}
                </div>
              )}
              {canCompose && <form className="record-note-form" onSubmit={save}>
                {replyingTo && <div className="reply-target"><span>{translate(language, 'alert.replyingTo', { name: visibleAuthorName(replyingTo) })}</span><button onClick={() => { setReplyingTo(null); setContent(''); }} type="button">{translate(language, 'common.cancel')}</button></div>}
                <label><span>{editingId ? translate(language, 'alert.editSharedNote') : replyingTo ? translate(language, 'alert.writeReply') : translate(language, 'alert.addSharedNote')}</span><textarea maxLength={600} onChange={(event) => setContent(event.target.value)} placeholder={translate(language, replyingTo ? 'alert.replyPlaceholder' : 'alert.sharedNotePlaceholder')} required rows={3} value={content} /></label>
                {!editingId && activeShareContext && <label className="record-note-share-option">
                  <span><input checked={shareWithFarmChat} onChange={(event) => setShareWithFarmChat(event.target.checked)} type="checkbox" /> {translate(language, 'chat.shareMiteOption')}</span>
                  <small>{translate(language, 'chat.shareMiteHelp')}</small>
                </label>}
                <div>{editingId && <button className="cancel" onClick={() => { setEditingId(''); setContent(''); }} type="button">{translate(language, 'common.cancel')}</button>}<button disabled={sending || !content.trim()} type="submit">{translate(language, editingId ? 'alert.updateSharedNote' : replyingTo ? 'alert.saveReply' : 'alert.saveSharedNote')}</button></div>
              </form>}
            </>
          )}
          {message && <div className="review-feedback success" role="status">{message}</div>}
          {error && <div className="review-feedback error" role="alert">{error}</div>}
        </div>
      )}
    </section>
  );
}
