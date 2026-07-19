/**
 * Resolve live Automation / menu chords from profile overrides + defaults.
 */

import {
  HOTKEY_ACTION_LABELS,
  HOTKEY_ACTIONS,
  HOTKEY_DEFAULTS,
  NOVA_ACTION_KIND_LABELS,
  SHORTCUTS_MENU_BINDING,
  type HotkeyAction,
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

export function getEffectiveAutomationBindings(
  profile: Pick<HotkeyProfile, 'automationBindings'> | null | undefined,
): Record<HotkeyAction, HotkeyBinding> {
  const out = { ...HOTKEY_DEFAULTS };
  const overrides = profile?.automationBindings;
  if (!overrides) return out;
  for (const action of HOTKEY_ACTIONS) {
    const chord = overrides[action];
    if (!chord) continue;
    const binding = chordToBinding(chord);
    if (binding) out[action] = binding;
  }
  return out;
}

export function getEffectiveMenuBinding(
  profile: Pick<HotkeyProfile, 'shortcutsMenuKey'> | null | undefined,
): HotkeyBinding {
  const chord = profile?.shortcutsMenuKey;
  if (!chord) return SHORTCUTS_MENU_BINDING;
  return chordToBinding(chord) ?? SHORTCUTS_MENU_BINDING;
}

export function collectOccupiedSlots(
  automation: Record<HotkeyAction, HotkeyBinding>,
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
  for (const action of HOTKEY_ACTIONS) {
    slots.push({
      id: `auto_${action}`,
      label: HOTKEY_ACTION_LABELS[action],
      chord: bindingToChord(automation[action]),
    });
  }
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
