/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import { deleteSelectedDrawingOnKey, shouldDeleteSelectedDrawing } from './chartDrawingKeys';

function keyEvent(
  key: string,
  opts: {
    code?: string;
    ctrl?: boolean;
    shift?: boolean;
    alt?: boolean;
    meta?: boolean;
    repeat?: boolean;
    target?: EventTarget;
  } = {},
): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    key,
    code: opts.code,
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

describe('shouldDeleteSelectedDrawing', () => {
  it('deletes on Delete when a drawing is selected', () => {
    expect(shouldDeleteSelectedDrawing(keyEvent('Delete'), true)).toBe(true);
  });

  it('deletes on Backspace so laptop keyboards without a dedicated Delete still work', () => {
    expect(shouldDeleteSelectedDrawing(keyEvent('Backspace'), true)).toBe(true);
  });

  it('does nothing when no drawing is selected', () => {
    expect(shouldDeleteSelectedDrawing(keyEvent('Delete'), false)).toBe(false);
  });

  it('does not steal Shift+Backspace (cancel-orders Nova Action)', () => {
    expect(
      shouldDeleteSelectedDrawing(keyEvent('Backspace', { shift: true }), true),
    ).toBe(false);
  });

  it('does not fire while typing in an input', () => {
    expect(
      shouldDeleteSelectedDrawing(
        keyEvent('Delete', { target: document.createElement('input') }),
        true,
      ),
    ).toBe(false);
  });

  it('ignores key repeat', () => {
    expect(shouldDeleteSelectedDrawing(keyEvent('Delete', { repeat: true }), true)).toBe(
      false,
    );
  });
});

describe('deleteSelectedDrawingOnKey', () => {
  it('removes the selected drawing on Delete', () => {
    const removeDrawing = vi.fn();
    const manager = {
      getSelectedDrawing: () => ({ id: 'verticalline-1' }),
      removeDrawing,
    };
    const event = keyEvent('Delete');
    expect(deleteSelectedDrawingOnKey(manager, event)).toBe(true);
    expect(removeDrawing).toHaveBeenCalledWith('verticalline-1');
    expect(event.defaultPrevented).toBe(true);
  });

  it('does not remove when nothing is selected', () => {
    const removeDrawing = vi.fn();
    const manager = {
      getSelectedDrawing: () => null,
      removeDrawing,
    };
    expect(deleteSelectedDrawingOnKey(manager, keyEvent('Delete'))).toBe(false);
    expect(removeDrawing).not.toHaveBeenCalled();
  });
});
