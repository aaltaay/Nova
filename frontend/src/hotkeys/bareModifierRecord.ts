/**
 * Capture modifier-only chords during rebind (Alt, Ctrl+Alt, …).
 * TanStack's recorder ignores modifier-only keydowns — this fills that gap.
 */

import {
  bindingFromModifiers,
  formatHotkeyLabel,
  modifierFromKeyboardEvent,
  type ModifierName,
} from '../hooks/hotkeyUtils';
import type { HotkeyKeyChord } from './types';

export type BareModifierRecordState = {
  /** Modifiers seen in this gesture (order-independent set). */
  armed: Set<ModifierName>;
  /** How many chord modifiers are still physically down. */
  down: number;
  /** True once a non-modifier was pressed — TanStack owns the chord. */
  contaminated: boolean;
};

export function initialBareModifierRecordState(): BareModifierRecordState {
  return { armed: new Set(), down: 0, contaminated: false };
}

export function reduceBareModifierRecordKeyDown(
  state: BareModifierRecordState,
  event: Pick<KeyboardEvent, 'key' | 'code' | 'repeat'>,
): BareModifierRecordState {
  if (event.repeat) return state;
  const mod = modifierFromKeyboardEvent(event);
  if (mod) {
    if (state.contaminated) return state;
    if (state.armed.has(mod)) return state;
    const armed = new Set(state.armed);
    armed.add(mod);
    return { armed, down: state.down + 1, contaminated: false };
  }
  if (event.key === 'Escape') return state;
  return { armed: new Set(), down: 0, contaminated: true };
}

export function reduceBareModifierRecordKeyUp(
  state: BareModifierRecordState,
  event: Pick<KeyboardEvent, 'key' | 'code'>,
): { state: BareModifierRecordState; chord: HotkeyKeyChord | null } {
  const mod = modifierFromKeyboardEvent(event);
  if (!mod || !state.armed.has(mod)) return { state, chord: null };

  const down = Math.max(0, state.down - 1);
  if (down > 0) {
    return { state: { ...state, down }, chord: null };
  }

  // Last modifier of the gesture released.
  if (state.contaminated || state.armed.size === 0) {
    return { state: initialBareModifierRecordState(), chord: null };
  }

  const binding = bindingFromModifiers(state.armed);
  const chord: HotkeyKeyChord = {
    key: binding.key,
    label: formatHotkeyLabel(binding),
    ctrl: binding.ctrl,
    shift: binding.shift,
    alt: binding.alt,
    meta: binding.meta,
  };
  return { state: initialBareModifierRecordState(), chord };
}
