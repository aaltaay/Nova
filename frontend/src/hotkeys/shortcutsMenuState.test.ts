/**
 * @vitest-environment jsdom
 */
import { describe, expect, it } from 'vitest';
import {
  initialShortcutsMenuState,
  reduceShortcutsMenuKeyDown,
  reduceShortcutsMenuKeyUp,
} from './shortcutsMenuState';

function ctrlM(overrides: Partial<KeyboardEvent> = {}): KeyboardEvent {
  return {
    key: 'm',
    ctrlKey: true,
    shiftKey: false,
    altKey: false,
    metaKey: false,
    repeat: false,
    target: document.body,
    ...overrides,
  } as KeyboardEvent;
}

describe('shortcutsMenuState', () => {
  it('opens peek on first Ctrl+M', () => {
    const { state, consumed } = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlM(),
      1000,
    );
    expect(consumed).toBe(true);
    expect(state.mode).toBe('peek');
  });

  it('closes peek on M keyup', () => {
    const open = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlM(),
      1000,
    ).state;
    const closed = reduceShortcutsMenuKeyUp(open, { key: 'm' } as KeyboardEvent);
    expect(closed.mode).toBe('closed');
    expect(closed.lastTapAt).toBe(1000);
  });

  it('pins on second Ctrl+M within double-tap window', () => {
    let state = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlM(),
      1000,
    ).state;
    state = reduceShortcutsMenuKeyUp(state, { key: 'm' } as KeyboardEvent);
    const pinned = reduceShortcutsMenuKeyDown(state, ctrlM(), 1200, 450);
    expect(pinned.consumed).toBe(true);
    expect(pinned.state.mode).toBe('pinned');
  });

  it('does not pin when second tap is too late', () => {
    let state = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlM(),
      1000,
    ).state;
    state = reduceShortcutsMenuKeyUp(state, { key: 'm' } as KeyboardEvent);
    const again = reduceShortcutsMenuKeyDown(state, ctrlM(), 2000, 450);
    expect(again.state.mode).toBe('peek');
  });

  it('keeps pinned open on keyup', () => {
    let state = reduceShortcutsMenuKeyDown(
      initialShortcutsMenuState(),
      ctrlM(),
      1000,
    ).state;
    state = reduceShortcutsMenuKeyUp(state, { key: 'm' } as KeyboardEvent);
    state = reduceShortcutsMenuKeyDown(state, ctrlM(), 1200, 450).state;
    expect(state.mode).toBe('pinned');
    const afterUp = reduceShortcutsMenuKeyUp(state, { key: 'm' } as KeyboardEvent);
    expect(afterUp.mode).toBe('pinned');
  });

  it('closes pinned on Escape or Ctrl+M', () => {
    const pinned = { mode: 'pinned' as const, lastTapAt: 100 };
    expect(
      reduceShortcutsMenuKeyDown(pinned, { key: 'Escape', repeat: false, target: document.body } as KeyboardEvent, 200)
        .state.mode,
    ).toBe('closed');
    expect(
      reduceShortcutsMenuKeyDown(pinned, ctrlM(), 200).state.mode,
    ).toBe('closed');
  });
});
