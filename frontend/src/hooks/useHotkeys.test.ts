/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import type { NovaActionRecord } from '../hotkeys/novaActionTypes';
import {
  createHotkeyKeydownHandler,
  eventMatchesBinding,
  isEditableTarget,
} from './hotkeyUtils';

function keyEvent(
  key: string,
  opts: { ctrl?: boolean; shift?: boolean; alt?: boolean; meta?: boolean; target?: EventTarget; repeat?: boolean } = {},
): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    key,
    ctrlKey: Boolean(opts.ctrl),
    shiftKey: Boolean(opts.shift),
    altKey: Boolean(opts.alt),
    metaKey: Boolean(opts.meta),
    repeat: Boolean(opts.repeat),
    bubbles: true,
    cancelable: true,
  });
  if (opts.target) {
    Object.defineProperty(event, 'target', { value: opts.target });
  }
  return event;
}

const CANCEL: NovaActionRecord = {
  id: 'a1',
  name: 'Cancel symbol',
  kind: 'cancel_symbol',
  key: { label: 'Shift+A', key: 'a', shift: true },
  params: {},
  enabled: true,
  showButton: false,
};

describe('isEditableTarget', () => {
  it('returns true for input and textarea', () => {
    expect(isEditableTarget(document.createElement('input'))).toBe(true);
    expect(isEditableTarget(document.createElement('textarea'))).toBe(true);
  });

  it('returns false for plain div', () => {
    expect(isEditableTarget(document.createElement('div'))).toBe(false);
  });
});

describe('eventMatchesBinding', () => {
  it('requires modifier flags to match exactly', () => {
    expect(eventMatchesBinding(keyEvent('a', { shift: true }), { key: 'a', shift: true })).toBe(true);
    expect(eventMatchesBinding(keyEvent('a'), { key: 'a', shift: true })).toBe(false);
  });
});

describe('createHotkeyKeydownHandler', () => {
  it('runs the matching enabled Nova Action', () => {
    const onNovaAction = vi.fn();
    const handler = createHotkeyKeydownHandler({ novaActions: [CANCEL], onNovaAction });
    const event = keyEvent('A', { shift: true });
    handler(event);
    expect(onNovaAction).toHaveBeenCalledWith(CANCEL);
    expect(event.defaultPrevented).toBe(true);
  });

  it('frees the retired Automation chords (Shift+A no longer approves a staged ticket)', () => {
    const onNovaAction = vi.fn();
    const handler = createHotkeyKeydownHandler({ novaActions: [], onNovaAction });
    const event = keyEvent('A', { shift: true });
    handler(event);
    expect(onNovaAction).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it('ignores disabled actions, typing and key repeat', () => {
    const onNovaAction = vi.fn();
    const handler = createHotkeyKeydownHandler({
      novaActions: [{ ...CANCEL, enabled: false }],
      onNovaAction,
    });
    handler(keyEvent('A', { shift: true }));
    const typing = createHotkeyKeydownHandler({ novaActions: [CANCEL], onNovaAction });
    typing(keyEvent('A', { shift: true, target: document.createElement('input') }));
    typing(keyEvent('A', { shift: true, repeat: true }));
    expect(onNovaAction).not.toHaveBeenCalled();
  });
});
