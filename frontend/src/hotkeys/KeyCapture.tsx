/**
 * One-shot keydown capture for binding a hotkey chord.
 */

import { useEffect } from 'react';
import { parseKeyChord } from './htkFormat';
import type { HotkeyKeyChord } from './types';

export function KeyCapture({
  onCapture,
  onCancel,
}: {
  onCapture: (c: HotkeyKeyChord) => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === 'Escape') {
        onCancel();
        return;
      }
      if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
      const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
      const parts: string[] = [];
      if (e.ctrlKey) parts.push('Ctrl');
      if (e.shiftKey) parts.push('Shift');
      if (e.altKey) parts.push('Alt');
      if (e.metaKey) parts.push('Win');
      parts.push(key === ' ' ? 'Space' : key);
      onCapture(parseKeyChord(parts.join('+')));
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => window.removeEventListener('keydown', onKeyDown, true);
  }, [onCapture, onCancel]);
  return null;
}
