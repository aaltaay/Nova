/**
 * Pure state machine for shortcuts-menu peek / double-tap pin.
 * Default trigger is Ctrl+Alt (hold = peek, release = close).
 */

import {
  SHORTCUTS_MENU_BINDING,
  SHORTCUTS_MENU_DOUBLE_TAP_MS,
  type HotkeyBinding,
} from '../constants';
import {
  eventMatchesBinding,
  isEditableTarget,
  isModifierOnlyBinding,
  modifierFromKeyboardEvent,
  modifiersFromBinding,
} from '../hooks/hotkeyUtils';

export type ShortcutsMenuMode = 'closed' | 'peek' | 'pinned';

export type ShortcutsMenuState = {
  mode: ShortcutsMenuMode;
  lastTapAt: number;
};

const MODIFIER_KEYS = new Set(['control', 'shift', 'alt', 'meta']);

export function initialShortcutsMenuState(): ShortcutsMenuState {
  return { mode: 'closed', lastTapAt: 0 };
}

export function isShortcutsMenuChord(
  event: KeyboardEvent,
  binding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): boolean {
  return eventMatchesBinding(event, binding);
}

function isModifierKeyName(key: string): boolean {
  return MODIFIER_KEYS.has(key.toLowerCase());
}

/** Keydown transition. Returns next state + whether the event was consumed. */
export function reduceShortcutsMenuKeyDown(
  state: ShortcutsMenuState,
  event: KeyboardEvent,
  nowMs: number,
  doubleTapMs: number = SHORTCUTS_MENU_DOUBLE_TAP_MS,
  menuBinding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): { state: ShortcutsMenuState; consumed: boolean } {
  if (event.repeat) return { state, consumed: false };

  // Escape / menu chord work even in inputs -- the cheat sheet must be
  // reachable while the ticker search box (or any field) has focus.
  if (event.key === 'Escape' && state.mode !== 'closed') {
    return { state: { mode: 'closed', lastTapAt: 0 }, consumed: true };
  }

  if (isShortcutsMenuChord(event, menuBinding)) {
    if (state.mode === 'pinned') {
      return { state: { mode: 'closed', lastTapAt: 0 }, consumed: true };
    }

    const withinDouble = state.lastTapAt > 0
      && nowMs - state.lastTapAt <= doubleTapMs;

    if (withinDouble) {
      return {
        state: { mode: 'pinned', lastTapAt: nowMs },
        consumed: true,
      };
    }

    return {
      state: { mode: 'peek', lastTapAt: nowMs },
      consumed: true,
    };
  }

  if (isEditableTarget(event.target)) return { state, consumed: false };

  // Hold menu modifier then press another key: drop peek so Alt/Ctrl+letter
  // chords keep working without the overlay stuck open.
  if (state.mode === 'peek' && !isModifierKeyName(event.key)) {
    return { state: { ...state, mode: 'closed' }, consumed: false };
  }

  return { state, consumed: false };
}

/** Keyup: dismiss peek when releasing any chord modifier (pinned stays open). */
export function reduceShortcutsMenuKeyUp(
  state: ShortcutsMenuState,
  event: KeyboardEvent,
  menuBinding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): ShortcutsMenuState {
  if (state.mode !== 'peek') return state;
  const pressed = modifierFromKeyboardEvent(event);

  if (isModifierOnlyBinding(menuBinding)) {
    const chord = modifiersFromBinding(menuBinding);
    if (pressed && chord.includes(pressed)) {
      return { ...state, mode: 'closed' };
    }
    return state;
  }

  const menuKey = menuBinding.key.toLowerCase();
  const key = event.key.toLowerCase();
  if (key === menuKey) {
    return { ...state, mode: 'closed' };
  }
  // Letter chords (e.g. legacy Ctrl+M): also close when the modifier lifts.
  if (pressed === 'control' || pressed === 'meta' || pressed === 'alt') {
    return { ...state, mode: 'closed' };
  }
  return state;
}
