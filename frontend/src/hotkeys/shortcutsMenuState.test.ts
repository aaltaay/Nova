/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  initialShortcutsMenuState,
  reduceShortcutsMenuKeyDown,
  reduceShortcutsMenuKeyUp,
} from './shortcutsMenuState';

function ctrlAltComplete(
  which: 'Control' | 'Alt',
  overrides: Partial<KeyboardEvent> = {},
): KeyboardEvent {
  return {
    key: which,
    code: which === 'Control' ? 'ControlLeft' : 'AltLeft',
    ctrlKey: true,
    shiftKey: false,
    altKey: true,
    metaKey: false,
    repeat: false,
    target: document.body,
    ...overrides,
  } as KeyboardEvent;
}

describe('shortcutsMenuState', () => {
  it('opens peek when Ctrl+Alt chord completes', () => {
    const { state, consumed } = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlAltComplete('Alt'),
      1000,
    );
    expect(consumed).toBe(true);
    expect(state.mode).toBe('peek');
  });

  it('does not open on Alt alone', () => {
    const { consumed, state } = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      {
        key: 'Alt',
        code: 'AltLeft',
        ctrlKey: false,
        altKey: true,
        shiftKey: false,
        metaKey: false,
        repeat: false,
        target: document.body,
      } as KeyboardEvent,
      1000,
    );
    expect(consumed).toBe(false);
    expect(state.mode).toBe('closed');
  });

  it('closes peek on Alt or Ctrl keyup', () => {
    const open = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlAltComplete('Alt'),
      1000,
    ).state;
    expect(
      reduceShortcutsMenuKeyUp(open, { key: 'Alt', code: 'AltLeft' } as KeyboardEvent)
        .mode,
    ).toBe('closed');
    const open2 = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlAltComplete('Control'),
      1000,
    ).state;
    expect(
      reduceShortcutsMenuKeyUp(open2, {
        key: 'Control',
        code: 'ControlLeft',
      } as KeyboardEvent).mode,
    ).toBe('closed');
  });

  it('pins on second Ctrl+Alt within double-tap window', () => {
    let state = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlAltComplete('Alt'),
      1000,
    ).state;
    state = reduceShortcutsMenuKeyUp(state, {
      key: 'Alt',
      code: 'AltLeft',
    } as KeyboardEvent);
    const pinned = reduceShortcutsMenuKeyDown(
      state,
      ctrlAltComplete('Alt'),
      1200,
      450,
    );
    expect(pinned.consumed).toBe(true);
    expect(pinned.state.mode).toBe('pinned');
  });

  it('opens peek even when an input has focus', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    const { state, consumed } = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlAltComplete('Alt', { target: input }),
      1000,
    );
    expect(consumed).toBe(true);
    expect(state.mode).toBe('peek');
    input.remove();
  });
});
