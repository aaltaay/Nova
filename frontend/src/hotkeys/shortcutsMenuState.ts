/**
 * Pure state machine for shortcuts-menu peek / double-tap pin.
 */

import {
  SHORTCUTS_MENU_BINDING,
  SHORTCUTS_MENU_DOUBLE_TAP_MS,
  type HotkeyBinding,
} from '../constants';
import { eventMatchesBinding, isEditableTarget } from '../hooks/hotkeyUtils';

export type ShortcutsMenuMode = 'closed' | 'peek' | 'pinned';

export type ShortcutsMenuState = {
  mode: ShortcutsMenuMode;
  lastTapAt: number;
};

export function initialShortcutsMenuState(): ShortcutsMenuState {
  return { mode: 'closed', lastTapAt: 0 };
}

export function isShortcutsMenuChord(
  event: KeyboardEvent,
  binding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): boolean {
  return eventMatchesBinding(event, binding);
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
  if (isEditableTarget(event.target)) return { state, consumed: false };

  if (event.key === 'Escape' && state.mode !== 'closed') {
    return { state: { mode: 'closed', lastTapAt: 0 }, consumed: true };
  }

  if (!isShortcutsMenuChord(event, menuBinding)) {
    return { state, consumed: false };
  }

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

/** Keyup: dismiss peek when releasing the menu key or Ctrl (pinned stays open). */
export function reduceShortcutsMenuKeyUp(
  state: ShortcutsMenuState,
  event: KeyboardEvent,
  menuBinding: HotkeyBinding = SHORTCUTS_MENU_BINDING,
): ShortcutsMenuState {
  if (state.mode !== 'peek') return state;
  const key = event.key.toLowerCase();
  const menuKey = menuBinding.key.toLowerCase();
  if (key === menuKey || key === 'control' || key === 'meta') {
    return { ...state, mode: 'closed' };
  }
  return state;
}
