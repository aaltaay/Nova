import { describe, expect, it, vi } from 'vitest';
import { applySingleInstance, focusExistingWindow } from '../../electron/singleInstance.mjs';

describe('applySingleInstance', () => {
  it('returns false when another Nova already holds the lock', () => {
    const app = {
      requestSingleInstanceLock: () => false,
      on: vi.fn(),
    };
    expect(applySingleInstance(app, vi.fn())).toBe(false);
    expect(app.on).not.toHaveBeenCalled();
  });

  it('focuses the existing window on a second electron . launch', () => {
    const listeners = new Map<string, (() => void)[]>();
    const onSecond = vi.fn();
    const app = {
      requestSingleInstanceLock: () => true,
      on: (event: string, fn: () => void) => {
        const list = listeners.get(event) ?? [];
        list.push(fn);
        listeners.set(event, list);
      },
    };
    expect(applySingleInstance(app, onSecond)).toBe(true);
    listeners.get('second-instance')?.[0]?.();
    expect(onSecond).toHaveBeenCalledOnce();
  });
});

describe('focusExistingWindow', () => {
  it('recovers then shows a minimized window', () => {
    const recover = vi.fn();
    const win = {
      isDestroyed: () => false,
      isMinimized: () => true,
      restore: vi.fn(),
      show: vi.fn(),
      focus: vi.fn(),
    };
    expect(focusExistingWindow(win, recover)).toBe(true);
    expect(recover).toHaveBeenCalledWith(win);
    expect(win.restore).toHaveBeenCalledOnce();
    expect(win.show).toHaveBeenCalledOnce();
    expect(win.focus).toHaveBeenCalledOnce();
  });

  it('skips a destroyed window', () => {
    expect(focusExistingWindow({ isDestroyed: () => true }, vi.fn())).toBe(false);
  });
});
