/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { HOTKEY_DEFAULTS, HOTKEY_SIGNAL_BLOCKED_MESSAGE } from '../constants';
import {
  createHotkeyKeydownHandler,
  eventMatchesBinding,
  hotkeysAllowed,
  isEditableTarget,
  resolveHotkeyAction,
} from './hotkeyUtils';

function keyEvent(
  key: string,
  opts: { ctrl?: boolean; shift?: boolean; alt?: boolean; meta?: boolean; target?: EventTarget } = {},
): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    key,
    ctrlKey: Boolean(opts.ctrl),
    shiftKey: Boolean(opts.shift),
    altKey: Boolean(opts.alt),
    metaKey: Boolean(opts.meta),
    bubbles: true,
    cancelable: true,
  });
  if (opts.target) {
    Object.defineProperty(event, 'target', { value: opts.target });
  }
  return event;
}

describe('hotkeysAllowed', () => {
  it('blocks order actions in signal mode', () => {
    expect(hotkeysAllowed('signal', 'approve_staged')).toBe(false);
    expect(hotkeysAllowed('signal', 'reject_staged')).toBe(false);
    expect(hotkeysAllowed('signal', 'arm_confirm')).toBe(false);
  });

  it('allows order actions in confirm and auto_paper', () => {
    expect(hotkeysAllowed('confirm', 'approve_staged')).toBe(true);
    expect(hotkeysAllowed('auto_paper', 'approve_staged')).toBe(true);
  });

  it('allows non-order actions in signal mode', () => {
    expect(hotkeysAllowed('signal', 'disarm_signal')).toBe(true);
    expect(hotkeysAllowed('signal', 'focus_flatten')).toBe(true);
    expect(hotkeysAllowed('signal', 'kill_switch')).toBe(true);
  });
});

describe('isEditableTarget', () => {
  it('returns true for input and textarea', () => {
    expect(isEditableTarget(document.createElement('input'))).toBe(true);
    expect(isEditableTarget(document.createElement('textarea'))).toBe(true);
  });

  it('returns false for plain div', () => {
    expect(isEditableTarget(document.createElement('div'))).toBe(false);
  });
});

describe('resolveHotkeyAction', () => {
  it('maps Shift+A to approve_staged', () => {
    const event = keyEvent('A', { shift: true });
    expect(resolveHotkeyAction(event)).toBe('approve_staged');
  });

  it('returns null for unrelated keys', () => {
    expect(resolveHotkeyAction(keyEvent('z'))).toBeNull();
  });
});

describe('eventMatchesBinding', () => {
  it('requires modifier flags to match exactly', () => {
    const binding = HOTKEY_DEFAULTS.arm_confirm;
    expect(eventMatchesBinding(keyEvent('c', { shift: true, ctrl: true }), binding)).toBe(true);
    expect(eventMatchesBinding(keyEvent('c', { shift: true }), binding)).toBe(false);
  });
});

describe('createHotkeyKeydownHandler', () => {
  it('invokes callback when key matches and not typing', () => {
    const approve = vi.fn();
    const handler = createHotkeyKeydownHandler({
      mode: 'confirm',
      callbacks: { approve_staged: approve },
    });

    handler(keyEvent('A', { shift: true }));
    expect(approve).toHaveBeenCalledOnce();
  });

  it('ignores keydown when target is an input', () => {
    const approve = vi.fn();
    const handler = createHotkeyKeydownHandler({
      mode: 'confirm',
      callbacks: { approve_staged: approve },
    });

    handler(keyEvent('A', { shift: true, target: document.createElement('input') }));
    expect(approve).not.toHaveBeenCalled();
  });

  it('calls onBlocked in signal mode for order hotkeys', () => {
    const approve = vi.fn();
    const onBlocked = vi.fn();
    const handler = createHotkeyKeydownHandler({
      mode: 'signal',
      callbacks: { approve_staged: approve },
      onBlocked,
    });

    handler(keyEvent('A', { shift: true }));
    expect(approve).not.toHaveBeenCalled();
    expect(onBlocked).toHaveBeenCalledWith('approve_staged', HOTKEY_SIGNAL_BLOCKED_MESSAGE);
  });

  it('ignores key repeat (held key must not resend)', () => {
    const approve = vi.fn();
    const handler = createHotkeyKeydownHandler({
      mode: 'confirm',
      callbacks: { approve_staged: approve },
    });
    const event = keyEvent('A', { shift: true });
    Object.defineProperty(event, 'repeat', { value: true });
    handler(event);
    expect(approve).not.toHaveBeenCalled();
  });
});
