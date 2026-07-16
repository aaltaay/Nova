import {
  HOTKEY_DEFAULTS,
  HOTKEY_ORDER_ACTIONS,
  HOTKEY_SIGNAL_BLOCKED_MESSAGE,
  type HotkeyAction,
  type HotkeyBinding,
} from '../constants';

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

/** Resolve which hotkey action (if any) a keydown event maps to. */
export function resolveHotkeyAction(event: KeyboardEvent): HotkeyAction | null {
  for (const action of Object.keys(HOTKEY_DEFAULTS) as HotkeyAction[]) {
    if (eventMatchesBinding(event, HOTKEY_DEFAULTS[action])) return action;
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

/** Pure keydown handler — used by useHotkeys and unit tests. */
export function createHotkeyKeydownHandler(options: {
  mode: string;
  callbacks: HotkeyCallbacks;
  onBlocked?: (action: HotkeyAction, message: string) => void;
}): (event: KeyboardEvent) => void {
  const { mode, callbacks, onBlocked } = options;
  return (event: KeyboardEvent) => {
    if (isEditableTarget(event.target)) return;

    const action = resolveHotkeyAction(event);
    if (!action) return;

    if (!hotkeysAllowed(mode, action)) {
      event.preventDefault();
      onBlocked?.(action, HOTKEY_SIGNAL_BLOCKED_MESSAGE);
      return;
    }

    const handler = callbacks[action];
    if (!handler) return;

    event.preventDefault();
    handler();
  };
}
