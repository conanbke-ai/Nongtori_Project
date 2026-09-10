import { useEffect, useRef, useState } from 'react';

const INTERACTIVE_SELECTOR = [
  'a',
  'button',
  'select',
  'summary',
  '[role="button"]',
  '[data-tori-interactive]'
].join(',');

export function ToriCatPawCursor() {
  const cursorRef = useRef<HTMLDivElement | null>(null);
  const boingTimerRef = useRef<number | null>(null);
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const finePointer = window.matchMedia('(pointer: fine)');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    const syncEnabled = () => setEnabled(finePointer.matches);
    syncEnabled();
    finePointer.addEventListener('change', syncEnabled);

    const cursor = cursorRef.current;
    if (!cursor || !finePointer.matches) {
      return () => finePointer.removeEventListener('change', syncEnabled);
    }

    let lastX = -80;
    let lastY = -80;
    let frame = 0;

    const syncInteractive = (target: EventTarget | Element | null) => {
      const element = target instanceof Element ? target : null;
      const isTextInput = !!element?.closest('input,textarea,[contenteditable="true"]');
      cursor.classList.toggle('is-text', isTextInput);
      cursor.classList.toggle(
        'is-interactive',
        !isTextInput && !!element?.closest(INTERACTIVE_SELECTOR)
      );
    };

    const syncAtPointer = () => {
      frame = 0;
      syncInteractive(document.elementFromPoint(lastX, lastY));
    };

    const onMove = (event: PointerEvent) => {
      lastX = event.clientX;
      lastY = event.clientY;
      cursor.style.left = `${lastX}px`;
      cursor.style.top = `${lastY}px`;
      cursor.classList.add('is-visible');
      syncInteractive(event.target);
    };

    const onDown = (event: PointerEvent) => {
      const element = event.target instanceof Element ? event.target : null;
      if (element?.closest('input,textarea,[contenteditable="true"]')) return;
      cursor.classList.remove('is-boing');
      void cursor.offsetWidth;
      cursor.classList.add('is-boing');
      if (boingTimerRef.current) window.clearTimeout(boingTimerRef.current);
      boingTimerRef.current = window.setTimeout(
        () => cursor.classList.remove('is-boing'),
        reducedMotion.matches ? 120 : 560
      );
    };

    const onScroll = () => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(syncAtPointer);
    };
    const hide = () => cursor.classList.remove('is-visible');

    document.addEventListener('pointermove', onMove, { passive: true });
    document.addEventListener('pointerdown', onDown, { passive: true });
    document.addEventListener('scroll', onScroll, { passive: true, capture: true });
    document.documentElement.addEventListener('mouseleave', hide);
    window.addEventListener('blur', hide);

    return () => {
      finePointer.removeEventListener('change', syncEnabled);
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('scroll', onScroll, true);
      document.documentElement.removeEventListener('mouseleave', hide);
      window.removeEventListener('blur', hide);
      if (frame) window.cancelAnimationFrame(frame);
      if (boingTimerRef.current) window.clearTimeout(boingTimerRef.current);
    };
  }, [enabled]);

  useEffect(() => {
    document.documentElement.classList.toggle('tori-cursor-enabled', enabled);
    return () => document.documentElement.classList.remove('tori-cursor-enabled');
  }, [enabled]);

  if (!enabled) return null;

  return (
    <div ref={cursorRef} className="tori-cat-cursor" aria-hidden="true">
      <div className="tori-cat-cursor__paw">
        <svg viewBox="0 0 64 64" focusable="false" role="presentation">
          <ellipse className="tori-cat-cursor__bean bean-1" cx="14" cy="24" rx="7" ry="9" transform="rotate(-28 14 24)" />
          <ellipse className="tori-cat-cursor__bean bean-2" cx="27" cy="14" rx="7" ry="9" transform="rotate(-10 27 14)" />
          <ellipse className="tori-cat-cursor__bean bean-3" cx="42" cy="14" rx="7" ry="9" transform="rotate(10 42 14)" />
          <ellipse className="tori-cat-cursor__bean bean-4" cx="54" cy="25" rx="7" ry="9" transform="rotate(28 54 25)" />
          <path
            className="tori-cat-cursor__pad"
            d="M14 42C14 34 19 29 25 31C28 32 30 36 32 38C34 36 37 32 40 31C46 29 51 34 51 42C51 49 47 55 42 58C38 60 35 57 32 54C29 57 26 60 22 58C17 55 14 49 14 42Z"
          />
        </svg>
      </div>
      <span className="tori-cat-cursor__pop">뾰잉!</span>
    </div>
  );
}
