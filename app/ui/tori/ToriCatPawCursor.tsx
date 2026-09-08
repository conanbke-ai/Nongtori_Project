'use client';

// The shared implementation stays byte-for-byte identical to its pinned source.
import { ToriCatPawCursor as SharedToriCatPawCursor } from '@/vendor/tori-ui/ToriCatPawCursor';
import '@/vendor/tori-ui/tori-cursor.css';
import './cursor-theme.css';

export function ToriCatPawCursor() {
  return <SharedToriCatPawCursor />;
}
