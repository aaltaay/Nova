import {
  HOTKEY_DEFAULTS,
  HOTKEY_ORDER_ACTIONS,
  HOTKEY_SIGNAL_BLOCKED_MESSAGE,
  type HotkeyAction,
  type HotkeyBinding,
} from '../constants';
import type { HotkeyKeyChord } from '../hotkeys/types';
import type { NovaActionRecord } from '../hotkeys/novaActionTypes';

export type HotkeyCallbacks = Partial<Record<HotkeyAction, () => void>>;

/** True when the focused element is a text field — hotkeys must not fire. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest('[contenteditable="true"]'));
}

/** Order hotkeys are no-ops in signal mode; emergency / mode-drop keys stay available. */
export function hotkeysAllowed(mode: string, action: HotkeyAction): boolean {
  if (mode === 'signal' && HOTKEY_ORDER_ACTIONS.includes(action)) {
    return false;
  }
  return true;
}

export function eventMatchesBinding(event: KeyboardEvent, binding: HotkeyBinding): boolean {
  if (event.key.toLowerCase() !== binding.key.toLowerCase()) return false;
  return (
    event.ctrlKey === Boolean(binding.ctrl) &&
    event.shiftKey === Boolean(binding.shift) &&
    event.altKey === Boolean(binding.alt) &&
    event.metaKey === Boolean(binding.meta)
  );
}

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

export function eventMatchesChord(event: KeyboardEvent, chord: HotkeyKeyChord): boolean {
  const binding = chordToBinding(chord);
  if (!binding) return false;
  // Backspace alias: DAS uses "bkspace" / "Backspace"
  const eventKey = event.key === 'Backspace' ? 'backspace' : event.key.toLowerCase();
  const bindKey = binding.key.toLowerCase() === 'bkspace' ? 'backspace' : binding.key.toLowerCase();
  if (eventKey !== bindKey) return false;
  return (
    event.ctrlKey === Boolean(binding.ctrl) &&
    event.shiftKey === Boolean(binding.shift) &&
    event.altKey === Boolean(binding.alt) &&
    event.metaKey === Boolean(binding.meta)
  );
}

/** Resolve which hotkey action (if any) a keydown event maps to. */
export function resolveHotkeyAction(
  event: KeyboardEvent,
  bindings: Record<HotkeyAction, HotkeyBinding> = HOTKEY_DEFAULTS,
): HotkeyAction | null {
  for (const action of Object.keys(bindings) as HotkeyAction[]) {
    if (eventMatchesBinding(event, bindings[action])) return action;
  }
  return null;
}

/** First enabled Nova Action whose chord matches the event. */
export function resolveNovaAction(
  event: KeyboardEvent,
  actions: NovaActionRecord[],
): NovaActionRecord | null {
  for (const action of actions) {
    if (!action.enabled) continue;
    if (eventMatchesChord(event, action.key)) return action;
  }
  return null;
}

export function formatHotkeyLabel(binding: HotkeyBinding): string {
  const parts: string[] = [];
  if (binding.ctrl) parts.push('Ctrl');
  if (binding.shift) parts.push('Shift');
  if (binding.alt) parts.push('Alt');
  if (binding.meta) parts.push('Win');
  parts.push(binding.key.length === 1 ? binding.key.toUpperCase() : binding.key);
  return parts.join('+');
}

export function chordsConflict(a: HotkeyKeyChord, b: HotkeyKeyChord): boolean {
  const ba = chordToBinding(a);
  const bb = chordToBinding(b);
  if (!ba || !bb) return false;
  return (
    ba.key.toLowerCase() === bb.key.toLowerCase()
    && Boolean(ba.ctrl) === Boolean(bb.ctrl)
    && Boolean(ba.shift) === Boolean(bb.shift)
    && Boolean(ba.alt) === Boolean(bb.alt)
    && Boolean(ba.meta) === Boolean(bb.meta)
  );
}

/** Pure keydown handler — used by useHotkeys and unit tests. */
export function createHotkeyKeydownHandler(options: {
  mode: string;
  callbacks: HotkeyCallbacks;
  onBlocked?: (action: HotkeyAction, message: string) => void;
  /** Optional Nova Actions resolved after Automation six. */
  novaActions?: NovaActionRecord[];
  onNovaAction?: (action: NovaActionRecord) => void;
  /** Live Automation bindings (defaults to HOTKEY_DEFAULTS). */
  automationBindings?: Record<HotkeyAction, HotkeyBinding>;
}): (event: KeyboardEvent) => void {
  const {
    mode,
    callbacks,
    onBlocked,
    novaActions,
    onNovaAction,
    automationBindings = HOTKEY_DEFAULTS,
  } = options;
  return (event: KeyboardEvent) => {
    if (event.repeat) return;
    if (isEditableTarget(event.target)) return;

    const action = resolveHotkeyAction(event, automationBindings);
    if (action) {
      if (!hotkeysAllowed(mode, action)) {
        event.preventDefault();
        onBlocked?.(action, HOTKEY_SIGNAL_BLOCKED_MESSAGE);
        return;
      }
      const handler = callbacks[action];
      if (!handler) return;
      event.preventDefault();
      handler();
      return;
    }

    if (novaActions && onNovaAction) {
      const nova = resolveNovaAction(event, novaActions);
      if (nova) {
        event.preventDefault();
        onNovaAction(nova);
      }
    }
  };
}
