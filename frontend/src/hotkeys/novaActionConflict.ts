/**
 * Chord conflict checks for Nova Actions vs Automation defaults.
 */

import { HOTKEY_DEFAULTS, type HotkeyAction } from '../constants';
import { chordsConflict, formatHotkeyLabel, chordToBinding } from '../hooks/hotkeyUtils';
import { formatKeyChord } from './htkFormat';
import type { NovaActionRecord } from './novaActionTypes';
import type { HotkeyKeyChord } from './types';

function automationChords(): HotkeyKeyChord[] {
  return (Object.keys(HOTKEY_DEFAULTS) as HotkeyAction[]).map((a) => {
    const b = HOTKEY_DEFAULTS[a];
    return {
      label: formatHotkeyLabel(b),
      key: b.key,
      ctrl: b.ctrl,
      shift: b.shift,
      alt: b.alt,
      meta: b.meta,
    };
  });
}

/** Returns a human conflict message, or null if the chord is free / empty. */
export function novaActionConflictMessage(
  draft: NovaActionRecord,
  actions: NovaActionRecord[],
): string | null {
  if (!chordToBinding(draft.key)) return null;
  for (const other of actions) {
    if (other.id === draft.id) continue;
    if (chordsConflict(draft.key, other.key)) {
      return `Conflicts with Nova Action "${other.name}"`;
    }
  }
  for (const ac of automationChords()) {
    if (chordsConflict(draft.key, ac)) {
      return `Conflicts with Automation shortcut ${formatKeyChord(ac)}`;
    }
  }
  return null;
}
