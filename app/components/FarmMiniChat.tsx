'use client';

import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { languageNames, localeForLanguage, translate, type Language } from '@/app/lib/i18n';

type ChatRoom = 'farm' | 'community';

type ChatMessage = {
  id: string;
  author_name_snapshot: string;
  author_role_snapshot: string;
  author_account_snapshot: string;
  language: Language;
  content: string;
  created_at: string;
  updated_at: string;
  is_mine: boolean;
  can_delete: boolean;
};

type RoomRows = Record<ChatRoom, ChatMessage[]>;

type BrowserTranslator = {
  translate: (content: string) => Promise<string>;
};

type BrowserTranslatorFactory = {
  availability?: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<string>;
  create: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<BrowserTranslator>;
};

function roleName(role: string, language: Language) {
  return role === 'ADMIN' ? translate(language, 'role.admin')
    : role === 'OWNER' ? translate(language, 'role.owner')
      : translate(language, 'role.worker');
}

function roleClass(role: string) {
  return role === 'ADMIN' ? 'role-admin' : role === 'OWNER' ? 'role-owner' : 'role-worker';
}

function formatTime(value: string, language: Language) {
  return new Intl.DateTimeFormat(localeForLanguage(language), {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

function visibleAuthorName(message: ChatMessage) {
  const name = message.author_name_snapshot.trim();
  return name && !name.includes('@') ? name : message.author_account_snapshot;
}

function visibleAuthorMeta(message: ChatMessage, language: Language) {
  const role = roleName(message.author_role_snapshot, language);
  return visibleAuthorName(message) === message.author_account_snapshot
    ? role
    : `${role} · ${message.author_account_snapshot}`;
}

function roomEndpoint(room: ChatRoom) {
  return room === 'farm' ? '/api/farm-chat-messages' : '/api/community-chat-messages';
}

function translationKey(message: ChatMessage, targetLanguage: Language) {
  return `${message.id}:${message.updated_at}:${targetLanguage}`;
}

function browserTranslatorFactory() {
  return (globalThis as typeof globalThis & { Translator?: BrowserTranslatorFactory }).Translator ?? null;
}

function browserTranslationLanguage(language: Language) {
  return language === 'zh-CN' ? 'zh' : language;
}

async function createBrowserTranslator(sourceLanguage: Language, targetLanguage: Language) {
  const factory = browserTranslatorFactory();
  if (!factory?.create) return null;
  const options = {
    sourceLanguage: browserTranslationLanguage(sourceLanguage),
    targetLanguage: browserTranslationLanguage(targetLanguage),
  };
  if (factory.availability) {
    const availability = await factory.availability(options);
    if (availability === 'unavailable' || availability === 'no') return null;
  }
  return factory.create(options);
}

export function FarmMiniChat({ farmId, farmName, language, open: requestedOpen, onOpenChange }: {
  farmId: string;
  farmName: string;
  language: Language;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = requestedOpen ?? internalOpen;
  const [room, setRoom] = useState<ChatRoom>('farm');
  const [rowsByRoom, setRowsByRoom] = useState<RoomRows>({ farm: [], community: [] });
  const [loadedRooms, setLoadedRooms] = useState<Record<ChatRoom, boolean>>({ farm: false, community: false });
  const [content, setContent] = useState('');
  const [loadingRoom, setLoadingRoom] = useState<ChatRoom | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [unreadFarm, setUnreadFarm] = useState(0);
  const [translatedByKey, setTranslatedByKey] = useState<Map<string, string>>(() => new Map());
  const listRef = useRef<HTMLDivElement>(null);
  const scrollAfterLoad = useRef<ChatRoom | null>(null);
  const attemptedTranslations = useRef(new Set<string>());
  const translatorsByPair = useRef(new Map<string, Promise<BrowserTranslator | null>>());
  const translationQueues = useRef(new Map<string, Promise<void>>());

  const changeOpen = useCallback((nextOpen: boolean) => {
    setInternalOpen(nextOpen);
    onOpenChange?.(nextOpen);
  }, [onOpenChange]);

  const updateFarmUnread = useCallback((nextRows: ChatMessage[], viewing: boolean) => {
    const latest = nextRows[nextRows.length - 1];
    const storageKey = `farm-chat-seen:${farmId}`;
    if (!latest) {
      setUnreadFarm(0);
      return;
    }
    if (viewing) {
      window.localStorage.setItem(storageKey, latest.created_at);
      setUnreadFarm(0);
      return;
    }
    const seenAt = window.localStorage.getItem(storageKey);
    if (!seenAt) {
      window.localStorage.setItem(storageKey, latest.created_at);
      setUnreadFarm(0);
      return;
    }
    setUnreadFarm(nextRows.filter((message) => !message.is_mine && message.created_at > seenAt).length);
  }, [farmId]);

  const load = useCallback(async (targetRoom: ChatRoom, silent = false, scroll = false) => {
    if (!farmId) return;
    if (!silent) setLoadingRoom(targetRoom);
    try {
      const params = new URLSearchParams({ farmId });
      const response = await fetch(`${roomEndpoint(targetRoom)}?${params}`, { cache: 'no-store' });
      const result = await response.json() as { rows?: ChatMessage[]; error?: string };
      if (!response.ok) throw new Error(result.error || translate(language, 'chat.loadFailed'));
      const nextRows = result.rows ?? [];
      if (scroll) scrollAfterLoad.current = targetRoom;
      setRowsByRoom((current) => ({ ...current, [targetRoom]: nextRows }));
      setLoadedRooms((current) => ({ ...current, [targetRoom]: true }));
      if (targetRoom === 'farm') updateFarmUnread(nextRows, open && room === 'farm');
      if (!silent || targetRoom === room) setError('');
    } catch (caught) {
      if (!silent) setError(caught instanceof Error ? caught.message : translate(language, 'chat.loadFailed'));
    } finally {
      if (!silent) setLoadingRoom(null);
    }
  }, [farmId, language, open, room, updateFarmUnread]);

  useEffect(() => {
    if (!open || !farmId) return;
    const initialLoad = window.setTimeout(() => void load(room, false, true), 0);
    const refreshTimer = window.setInterval(
      () => void load(room, true),
      room === 'farm' ? 8000 : 12000,
    );
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(refreshTimer);
    };
  }, [farmId, load, open, room]);

  useEffect(() => {
    if (!farmId || (open && room === 'farm')) return;
    const initialLoad = window.setTimeout(() => void load('farm', true), 0);
    const refreshTimer = window.setInterval(() => void load('farm', true), 30000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(refreshTimer);
    };
  }, [farmId, load, open, room]);

  useEffect(() => {
    if (!open) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') changeOpen(false);
    }
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [changeOpen, open]);

  useEffect(() => {
    if (scrollAfterLoad.current !== room || !listRef.current) return;
    scrollAfterLoad.current = null;
    listRef.current.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [room, rowsByRoom]);

  const rows = rowsByRoom[room];

  useEffect(() => {
    if (!open) return;
    for (const message of rows) {
      if (message.language === language) continue;
      const cacheKey = translationKey(message, language);
      if (attemptedTranslations.current.has(cacheKey)) continue;
      attemptedTranslations.current.add(cacheKey);
      if (attemptedTranslations.current.size > 1000) {
        const oldest = attemptedTranslations.current.values().next().value as string | undefined;
        if (oldest) attemptedTranslations.current.delete(oldest);
      }

      const pairKey = `${message.language}:${language}`;
      let translatorPromise = translatorsByPair.current.get(pairKey);
      if (!translatorPromise) {
        translatorPromise = createBrowserTranslator(message.language, language).catch(() => null);
        translatorsByPair.current.set(pairKey, translatorPromise);
      }

      const previous = translationQueues.current.get(pairKey) ?? Promise.resolve();
      const task = previous.catch(() => undefined).then(async () => {
        try {
          const translator = await translatorPromise;
          if (!translator) return;
          const translated = (await translator.translate(message.content)).trim();
          if (!translated || translated === message.content.trim()) return;
          setTranslatedByKey((current) => {
            if (current.get(cacheKey) === translated) return current;
            const next = new Map(current);
            next.set(cacheKey, translated);
            while (next.size > 500) {
              const oldest = next.keys().next().value as string | undefined;
              if (!oldest) break;
              next.delete(oldest);
            }
            return next;
          });
        } catch {
          // 원문을 그대로 유지합니다.
        }
      });
      translationQueues.current.set(pairKey, task);
      void task.finally(() => {
        if (translationQueues.current.get(pairKey) === task) translationQueues.current.delete(pairKey);
      });
    }
  }, [language, open, rows]);

  function changeRoom(nextRoom: ChatRoom) {
    setRoom(nextRoom);
    setContent('');
    setError('');
    if (nextRoom === 'farm' && rowsByRoom.farm.length) updateFarmUnread(rowsByRoom.farm, true);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = content.trim();
    if (!message) return;
    setSending(true);
    setError('');
    try {
      const response = await fetch(roomEndpoint(room), {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ farmId, content: message, languageHint: language }),
      });
      const result = await response.json() as { error?: string };
      if (!response.ok) throw new Error(result.error || translate(language, 'chat.sendFailed'));
      setContent('');
      await load(room, true, true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'chat.sendFailed'));
    } finally {
      setSending(false);
    }
  }

  async function remove(message: ChatMessage) {
    if (!window.confirm(translate(language, 'chat.deleteConfirm'))) return;
    setSending(true);
    setError('');
    try {
      const params = new URLSearchParams({ farmId, messageId: message.id });
      const response = await fetch(`${roomEndpoint(room)}?${params}`, { method: 'DELETE' });
      const result = await response.json() as { error?: string };
      if (!response.ok) throw new Error(result.error || translate(language, 'chat.deleteFailed'));
      await load(room, true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : translate(language, 'chat.deleteFailed'));
    } finally {
      setSending(false);
    }
  }

  const loading = loadingRoom === room && !loadedRooms[room];
  const community = room === 'community';
  const maxLength = community ? 300 : 500;

  return (
    <aside className={`farm-mini-chat ${open ? 'open' : ''}`}>
      {!open && <button aria-expanded="false" aria-label={unreadFarm ? translate(language, 'chat.unread', { count: unreadFarm }) : translate(language, 'chat.open')} className="farm-chat-launcher" onClick={() => changeOpen(true)} type="button"><span aria-hidden="true" className="farm-chat-launcher-icon"><i>•••</i></span><b>{translate(language, 'chat.open')}</b>{unreadFarm > 0 && <em aria-hidden="true">{Math.min(unreadFarm, 99)}</em>}</button>}
      {open && <section aria-label={community ? translate(language, 'chat.communityTitle') : translate(language, 'chat.title')} className="farm-chat-drawer" role="dialog">
        <header><div><span>{community ? translate(language, 'chat.communityAudience') : farmName}</span><h2>{community ? translate(language, 'chat.communityTitle') : translate(language, 'chat.title')}</h2></div><button aria-label={translate(language, 'chat.close')} onClick={() => changeOpen(false)} title={translate(language, 'chat.close')} type="button">×</button></header>
        <div aria-label={translate(language, 'chat.roomLabel')} className="farm-chat-tabs" role="tablist">
          <button aria-selected={!community} className={!community ? 'selected' : ''} onClick={() => changeRoom('farm')} role="tab" type="button"><span>{translate(language, 'chat.farmTab')}</span>{unreadFarm > 0 && <b>{Math.min(unreadFarm, 99)}</b>}</button>
          <button aria-selected={community} className={community ? 'selected' : ''} onClick={() => changeRoom('community')} role="tab" type="button"><span>{translate(language, 'chat.communityTab')}</span></button>
        </div>
        <p className={`farm-chat-scope ${community ? 'community' : ''}`}>{translate(language, community ? 'chat.communityNotice' : 'chat.scope')}</p>
        <div aria-live="polite" className="farm-chat-messages" ref={listRef}>
          {loading ? <div className="farm-chat-empty">{translate(language, 'common.loading')}</div> : rows.length === 0 ? <div className="farm-chat-empty"><strong>{translate(language, 'chat.empty')}</strong><span>{translate(language, community ? 'chat.communityEmptyHelp' : 'chat.emptyHelp')}</span></div> : rows.map((message) => {
            const translated = translatedByKey.get(translationKey(message, language));
            return <article className={`${roleClass(message.author_role_snapshot)} ${message.is_mine ? 'mine' : ''}`} key={message.id}>
              <header><div><strong>{visibleAuthorName(message)}</strong><span>{visibleAuthorMeta(message, language)}</span></div><time>{formatTime(message.created_at, language)}</time></header>
              <p lang={translated ? language === 'zh-CN' ? 'zh' : language : message.language === 'zh-CN' ? 'zh' : message.language}>{translated ?? message.content}</p>
              {translated && <details className="farm-chat-original"><summary>{translate(language, 'chat.showOriginal')}</summary><p lang={message.language === 'zh-CN' ? 'zh' : message.language}>{message.content}</p></details>}
              <footer><span>{translated ? `${translate(language, 'chat.autoTranslated')} · ${languageNames[message.language] ?? message.language}` : languageNames[message.language] ?? message.language}</span>{message.can_delete && <button disabled={sending} onClick={() => void remove(message)} type="button">{translate(language, 'chat.delete')}</button>}</footer>
            </article>;
          })}
        </div>
        {error && <div className="farm-chat-error" role="alert">{error}</div>}
        <form onSubmit={send}><label><span className="sr-only">{translate(language, community ? 'chat.communityPlaceholder' : 'chat.placeholder')}</span><textarea maxLength={maxLength} onChange={(event) => setContent(event.target.value)} placeholder={translate(language, community ? 'chat.communityPlaceholder' : 'chat.placeholder')} rows={2} value={content} /></label><button disabled={sending || !content.trim()} type="submit">{translate(language, 'chat.send')}</button></form>
      </section>}
    </aside>
  );
}
