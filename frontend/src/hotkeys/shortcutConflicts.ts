/**
 * Duplicate detection using TanStack-normalized hotkey strings.
 */

import { chordToTanstackHotkey } from './tanstackChord';
import type { HotkeyKeyChord } from './types';

export type ShortcutConflictHit = {
  id: string;
  label: string;
  chord: string;
};

export type ShortcutOccupiedSlot = {
  id: string;
  label: string;
  chord: HotkeyKeyChord;
};

/** Find another binding that already owns this chord (library-normalized). */
export function findShortcutConflict(
  candidate: HotkeyKeyChord,
  occupied: ShortcutOccupiedSlot[],
  excludeId?: string,
): ShortcutConflictHit | null {
  const needle = chordToTanstackHotkey(candidate);
  if (!needle) return null;
  for (const slot of occupied) {
    if (excludeId && slot.id === excludeId) continue;
    const other = chordToTanstackHotkey(slot.chord);
    if (other && other === needle) {
      return {
        id: slot.id,
        label: slot.label,
        chord: other,
      };
    }
  }
  return null;
}
