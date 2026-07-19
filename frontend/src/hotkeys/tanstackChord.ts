/**
 * Adapters between Nova chords and TanStack Hotkeys strings.
 * Capture + normalize via @tanstack/hotkeys — do not hand-roll recorders.
 */

import {
  formatHotkey,
  normalizeHotkey,
  parseHotkey,
  type Hotkey,
} from '@tanstack/react-hotkeys';
import type { HotkeyBinding } from '../constants';
import { formatHotkeyLabel } from '../hooks/hotkeyUtils';
import type { HotkeyKeyChord } from './types';

/** Nova chord → canonical TanStack hotkey string (for conflict compare). */
export function chordToTanstackHotkey(chord: HotkeyKeyChord): string {
  const parts: string[] = [];
  if (chord.ctrl) parts.push('Control');
  if (chord.alt) parts.push('Alt');
  if (chord.shift) parts.push('Shift');
  if (chord.meta) parts.push('Meta');
  const key = chord.key?.trim();
  if (!key) return '';
  parts.push(key.length === 1 ? key.toUpperCase() : key);
  return normalizeHotkey(parts.join('+'));
}

export function bindingToTanstackHotkey(binding: HotkeyBinding): string {
  return chordToTanstackHotkey(bindingToChord(binding));
}

export function bindingToChord(binding: HotkeyBinding): HotkeyKeyChord {
  return {
    label: formatHotkeyLabel(binding),
    key: binding.key,
    ctrl: binding.ctrl,
    shift: binding.shift,
    alt: binding.alt,
    meta: binding.meta,
  };
}

/** TanStack recorder output → Nova chord (Windows-first Mod = Ctrl). */
export function tanstackHotkeyToChord(hotkey: Hotkey): HotkeyKeyChord {
  const parsed = parseHotkey(hotkey, 'windows');
  const key = parsed.key.length === 1 ? parsed.key.toLowerCase() : parsed.key;
  const chord: HotkeyKeyChord = {
    label: formatHotkey(parsed),
    key,
    ctrl: parsed.ctrl || undefined,
    shift: parsed.shift || undefined,
    alt: parsed.alt || undefined,
    meta: parsed.meta || undefined,
  };
  chord.label = formatHotkeyLabel({
    key: chord.key,
    ctrl: chord.ctrl,
    shift: chord.shift,
    alt: chord.alt,
    meta: chord.meta,
  });
  return chord;
}

export function chordsEqualTanstack(a: HotkeyKeyChord, b: HotkeyKeyChord): boolean {
  const ha = chordToTanstackHotkey(a);
  const hb = chordToTanstackHotkey(b);
  return Boolean(ha && hb && ha === hb);
}
