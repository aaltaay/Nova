import { describe, expect, it, vi } from 'vitest';
import { applySingleInstance, focusExistingWindow } from '../../electron/singleInstance.mjs';
import {
  createSeparateSimWindow, readOpenRequest, reviewWindowUrl, separateSimLocation,
} from '../../electron/openInNova.mjs';

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

  it('passes the second launch arguments so a nova://open link can be read', () => {
    const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
    const onSecond = vi.fn();
    const app = {
      requestSingleInstanceLock: () => true,
      on: (event: string, fn: (...args: unknown[]) => void) => {
        const list = listeners.get(event) ?? [];
        list.push(fn);
        listeners.set(event, list);
      },
    };
    applySingleInstance(app, onSecond);
    const argv = ['electron', 'nova://open?symbol=imcc&date=2026-09-18&as_of=10:00'];
    listeners.get('second-instance')?.[0]?.({}, argv);
    expect(onSecond).toHaveBeenCalledWith(argv);
    expect(readOpenRequest(argv)).toEqual({ symbol: 'IMCC', date: '2026-09-18', asOf: '10:00' });
  });
});

describe('open in nova urls', () => {
  it('builds a review window and refuses a url that is not that page', () => {
    expect(separateSimLocation('http://127.0.0.1:5173/', { symbol: 'IMCC', date: '2026-09-18', asOf: '10:00:00' }))
      .toBe('http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18&as_of=10%3A00');
    expect(reviewWindowUrl('/review?symbol=IMCC&date=2026-09-18&as_of=10:00', 'http://127.0.0.1:5173'))
      .toBe('http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18&as_of=10:00');
    expect(reviewWindowUrl('https://evil.example/review?symbol=IMCC&date=2026-09-18', 'http://127.0.0.1:5173')).toBeNull();
    expect(readOpenRequest(['nova://open?symbol=!!!&date=2026-09-18'])).toBeNull();
    const created: string[] = [];
    const win = createSeparateSimWindow(
      class {
        loadURL(url: string) { created.push(url); }
      },
      'http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18',
    );
    expect(created).toEqual(['http://127.0.0.1:5173/review?symbol=IMCC&date=2026-09-18']);
    expect(win).toBeTruthy();
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
