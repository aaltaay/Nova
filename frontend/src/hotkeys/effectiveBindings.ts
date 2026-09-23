/**
 * Resolve the live shortcuts-menu chord from profile overrides + defaults.
 */

import {
  NOVA_ACTION_KIND_LABELS,
  SHORTCUTS_MENU_BINDING,
  type HotkeyBinding,
} from '../constants';
import type { NovaActionRecord } from './novaActionTypes';
import type { ShortcutOccupiedSlot } from './shortcutConflicts';
import { bindingToChord, chordToTanstackHotkey } from './tanstackChord';
import type { HotkeyKeyChord, HotkeyProfile } from './types';

export function chordToBinding(chord: HotkeyKeyChord): HotkeyBinding | null {
  if (!chord.key) return null;
  return {
    key: chord.key,
    ctrl: chord.ctrl,
    shift: chord.shift,
    alt: chord.alt,
    meta: chord.meta,
  };
}

/**
 * Former defaults (Ctrl+M, bare Ctrl, bare Alt) — treat as unset so
 * hold-Ctrl+Alt ships for existing profiles that never intentionally rebound.
 */
function isLegacyMenuDefault(chord: HotkeyKeyChord): boolean {
  const key = chord.key.toLowerCase();
  const bare =
    !chord.shift && !chord.meta && !chord.ctrl && !chord.alt;
  if ((key === 'control' || key === 'alt') && bare) return true;
  return (
    key === 'm'
    && Boolean(chord.ctrl)
    && !chord.shift
    && !chord.alt
    && !chord.meta
  );
}

export function getEffectiveMenuBinding(
  profile: Pick<HotkeyProfile, 'shortcutsMenuKey'> | null | undefined,
): HotkeyBinding {
  const chord = profile?.shortcutsMenuKey;
  if (!chord || isLegacyMenuDefault(chord)) return SHORTCUTS_MENU_BINDING;
  return chordToBinding(chord) ?? SHORTCUTS_MENU_BINDING;
}

export function collectOccupiedSlots(
  novaActions: NovaActionRecord[],
  menuBinding: HotkeyBinding,
): ShortcutOccupiedSlot[] {
  const slots: ShortcutOccupiedSlot[] = [
    {
      id: 'menu:shortcuts_menu',
      label: 'Shortcuts menu',
      chord: bindingToChord(menuBinding),
    },
  ];
  for (const a of novaActions) {
    if (!a.key.key) continue;
    slots.push({
      id: a.id,
      label: a.name || NOVA_ACTION_KIND_LABELS[a.kind],
      chord: a.key,
    });
  }
  return slots;
}

/** Debug helper — unused in UI but handy in tests. */
export function occupiedTanstackKeys(
  slots: ShortcutOccupiedSlot[],
): string[] {
  return slots.map((s) => chordToTanstackHotkey(s.chord)).filter(Boolean);
}
