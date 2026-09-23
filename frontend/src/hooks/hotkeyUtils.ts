import type { HotkeyBinding } from '../constants';
import type { HotkeyKeyChord } from '../hotkeys/types';
import type { NovaActionRecord } from '../hotkeys/novaActionTypes';

/** True when the focused element is a text field — hotkeys must not fire. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest('[contenteditable="true"]'));
}

const MODIFIER_ONLY_KEYS = new Set(['control', 'shift', 'alt', 'meta']);

export type ModifierName = 'control' | 'shift' | 'alt' | 'meta';

/** Stable order for labels / TanStack strings (Control+Alt, not Alt+Control). */
export const MODIFIER_ORDER: ModifierName[] = [
  'control',
  'alt',
  'shift',
  'meta',
];

/** True when the binding's primary key is itself a modifier (Alt, Ctrl+Alt, …). */
export function isModifierOnlyBinding(binding: HotkeyBinding): boolean {
  return MODIFIER_ONLY_KEYS.has(binding.key.toLowerCase());
}

/**
 * Which modifier (if any) this keydown/keyup is for.
 * Uses `code` so AltLeft/AltRight still match when `key` is odd; skips AltGraph.
 */
export function modifierFromKeyboardEvent(
  event: Pick<KeyboardEvent, 'key' | 'code'>,
): ModifierName | null {
  const key = event.key.toLowerCase();
  const code = event.code;
  if (key === 'altgraph') return null;
  if (key === 'control' || code === 'ControlLeft' || code === 'ControlRight') {
    return 'control';
  }
  if (key === 'shift' || code === 'ShiftLeft' || code === 'ShiftRight') {
    return 'shift';
  }
  if (key === 'alt' || code === 'AltLeft' || code === 'AltRight') {
    return 'alt';
  }
  if (key === 'meta' || code === 'MetaLeft' || code === 'MetaRight') {
    return 'meta';
  }
  return null;
}

export function modifierFromKeyName(key: string): ModifierName | null {
  const k = key.toLowerCase();
  if (k === 'control' || k === 'ctrl') return 'control';
  if (k === 'shift') return 'shift';
  if (k === 'alt') return 'alt';
  if (k === 'meta' || k === 'win') return 'meta';
  return null;
}

export function canonicalModifierKey(mod: ModifierName): string {
  switch (mod) {
    case 'control':
      return 'Control';
    case 'shift':
      return 'Shift';
    case 'alt':
      return 'Alt';
    case 'meta':
      return 'Meta';
  }
}

export function modifierLabel(mod: ModifierName): string {
  switch (mod) {
    case 'control':
      return 'Ctrl';
    case 'shift':
      return 'Shift';
    case 'alt':
      return 'Alt';
    case 'meta':
      return 'Win';
  }
}

/** All modifiers implied by a binding (key + flags). */
export function modifiersFromBinding(binding: HotkeyBinding): ModifierName[] {
  const set = new Set<ModifierName>();
  const keyMod = modifierFromKeyName(binding.key);
  if (keyMod) set.add(keyMod);
  if (binding.ctrl) set.add('control');
  if (binding.shift) set.add('shift');
  if (binding.alt) set.add('alt');
  if (binding.meta) set.add('meta');
  return MODIFIER_ORDER.filter((m) => set.has(m));
}

/**
 * Build a binding from a modifier set.
 * Last modifier in MODIFIER_ORDER becomes `key`; earlier ones become flags
 * (so Ctrl+Alt → `{ key: 'Alt', ctrl: true }`, matching TanStack parse).
 */
export function bindingFromModifiers(mods: Iterable<ModifierName>): HotkeyBinding {
  const ordered = MODIFIER_ORDER.filter((m) => new Set(mods).has(m));
  if (ordered.length === 0) return { key: 'Alt' };
  const keyMod = ordered[ordered.length - 1]!;
  const binding: HotkeyBinding = { key: canonicalModifierKey(keyMod) };
  for (const m of ordered.slice(0, -1)) {
    if (m === 'control') binding.ctrl = true;
    if (m === 'shift') binding.shift = true;
    if (m === 'alt') binding.alt = true;
    if (m === 'meta') binding.meta = true;
  }
  return binding;
}

function heldModifiers(
  event: Pick<KeyboardEvent, 'ctrlKey' | 'shiftKey' | 'altKey' | 'metaKey'>,
): Set<ModifierName> {
  const held = new Set<ModifierName>();
  if (event.ctrlKey) held.add('control');
  if (event.shiftKey) held.add('shift');
  if (event.altKey) held.add('alt');
  if (event.metaKey) held.add('meta');
  return held;
}

/** Match Ctrl / Alt / Ctrl+Alt / … when the completing modifier keydown fires. */
export function eventMatchesModifierChord(
  event: KeyboardEvent,
  binding: HotkeyBinding,
): boolean {
  const chord = modifiersFromBinding(binding);
  if (chord.length === 0) return false;
  const pressed = modifierFromKeyboardEvent(event);
  if (!pressed || !chord.includes(pressed)) return false;
  const held = heldModifiers(event);
  for (const m of chord) {
    if (!held.has(m)) return false;
  }
  for (const m of held) {
    if (!chord.includes(m)) return false;
  }
  return true;
}

export function eventMatchesBinding(event: KeyboardEvent, binding: HotkeyBinding): boolean {
  if (isModifierOnlyBinding(binding)) {
    return eventMatchesModifierChord(event, binding);
  }

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
  const key = binding.key.toLowerCase() === 'bkspace' ? 'Backspace' : binding.key;
  return eventMatchesBinding(event, { ...binding, key });
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
  if (isModifierOnlyBinding(binding)) {
    return modifiersFromBinding(binding).map(modifierLabel).join('+');
  }
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
  if (isModifierOnlyBinding(ba) && isModifierOnlyBinding(bb)) {
    const sa = modifiersFromBinding(ba).join('+');
    const sb = modifiersFromBinding(bb).join('+');
    return sa === sb && sa.length > 0;
  }
  return (
    ba.key.toLowerCase() === bb.key.toLowerCase()
    && Boolean(ba.ctrl) === Boolean(bb.ctrl)
    && Boolean(ba.shift) === Boolean(bb.shift)
    && Boolean(ba.alt) === Boolean(bb.alt)
    && Boolean(ba.meta) === Boolean(bb.meta)
  );
}

/** Pure keydown handler for Nova Actions — used by the shell dispatcher and unit tests. */
export function createHotkeyKeydownHandler(options: {
  novaActions: NovaActionRecord[];
  onNovaAction: (action: NovaActionRecord) => void;
}): (event: KeyboardEvent) => void {
  const { novaActions, onNovaAction } = options;
  return (event: KeyboardEvent) => {
    if (event.repeat) return;
    if (isEditableTarget(event.target)) return;
    const nova = resolveNovaAction(event, novaActions);
    if (nova) {
      event.preventDefault();
      onNovaAction(nova);
    }
  };
}
