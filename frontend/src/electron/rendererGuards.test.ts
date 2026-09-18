import { describe, expect, it, vi } from 'vitest';
import {
  attachRendererGuards,
  needsRendererRecover,
  recoverWindowIfErrorPage,
  shouldBlockNavigation,
  shouldReloadAfterRendererGone,
} from '../../electron/rendererGuards.mjs';

describe('needsRendererRecover', () => {
  it('recovers empty, chrome-error, and about:blank', () => {
    expect(needsRendererRecover('')).toBe(true);
    expect(needsRendererRecover('chrome-error://chromewebdata/')).toBe(true);
    expect(needsRendererRecover('about:blank')).toBe(true);
  });

  it('keeps a live Vite renderer', () => {
    expect(needsRendererRecover('http://127.0.0.1:5173/')).toBe(false);
    expect(
      needsRendererRecover('http://127.0.0.1:5173/?view=stock&symbol=SPY'),
    ).toBe(false);
  });
});

describe('shouldBlockNavigation', () => {
  it('blocks chrome-error even when the base is Vite', () => {
    expect(
      shouldBlockNavigation(
        'chrome-error://chromewebdata/',
        'http://127.0.0.1:5173',
      ),
    ).toBe(true);
  });

  it('allows same-origin Vite query changes', () => {
    expect(
      shouldBlockNavigation(
        'http://127.0.0.1:5173/?view=stock&symbol=SPY',
        'http://127.0.0.1:5173',
      ),
    ).toBe(false);
  });

  it('blocks a different origin', () => {
    expect(
      shouldBlockNavigation('https://example.com/', 'http://127.0.0.1:5173'),
    ).toBe(true);
  });

  it('allows packaged file URLs', () => {
    expect(
      shouldBlockNavigation(
        'file:///C:/Nova/dist/index.html?view=stock&symbol=QQQ',
        'file:',
      ),
    ).toBe(false);
  });
});

describe('shouldReloadAfterRendererGone', () => {
  it('reloads crash / oom / launch-failed, not a clean exit', () => {
    expect(shouldReloadAfterRendererGone('crashed')).toBe(true);
    expect(shouldReloadAfterRendererGone('oom')).toBe(true);
    expect(shouldReloadAfterRendererGone('clean-exit')).toBe(false);
    expect(shouldReloadAfterRendererGone('killed')).toBe(false);
  });
});

describe('recoverWindowIfErrorPage', () => {
  it('reloads Vite when the window is on chrome-error', () => {
    const win = {
      isDestroyed: () => false,
      loadURL: vi.fn(),
      webContents: { getURL: () => 'chrome-error://chromewebdata/' },
    };
    expect(recoverWindowIfErrorPage(win, { reloadUrl: 'http://127.0.0.1:5173' })).toBe(
      true,
    );
    expect(win.loadURL).toHaveBeenCalledWith('http://127.0.0.1:5173');
  });

  it('leaves a healthy Vite window alone', () => {
    const win = {
      isDestroyed: () => false,
      loadURL: vi.fn(),
      webContents: { getURL: () => 'http://127.0.0.1:5173/' },
    };
    expect(recoverWindowIfErrorPage(win, { reloadUrl: 'http://127.0.0.1:5173' })).toBe(
      false,
    );
    expect(win.loadURL).not.toHaveBeenCalled();
  });
});

describe('attachRendererGuards', () => {
  it('prevents chrome-error navigation and recovers to Vite', () => {
    const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
    const win = {
      isDestroyed: () => false,
      loadURL: vi.fn(),
      webContents: {
        on: (event: string, fn: (...args: unknown[]) => void) => {
          const list = listeners.get(event) ?? [];
          list.push(fn);
          listeners.set(event, list);
        },
      },
    };
    attachRendererGuards(win, {
      allowedBase: 'http://127.0.0.1:5173',
      reloadUrl: 'http://127.0.0.1:5173',
      retryFail: true,
    });
    const ev = { preventDefault: vi.fn() };
    listeners.get('will-navigate')?.[0]?.(ev, 'chrome-error://chromewebdata/');
    expect(ev.preventDefault).toHaveBeenCalledOnce();
    expect(win.loadURL).toHaveBeenCalledWith('http://127.0.0.1:5173');
  });

  it('reloads after a renderer crash', () => {
    const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
    const win = {
      isDestroyed: () => false,
      loadURL: vi.fn(),
      webContents: {
        on: (event: string, fn: (...args: unknown[]) => void) => {
          const list = listeners.get(event) ?? [];
          list.push(fn);
          listeners.set(event, list);
        },
      },
    };
    attachRendererGuards(win, {
      allowedBase: 'http://127.0.0.1:5173',
      reloadUrl: 'http://127.0.0.1:5173',
    });
    listeners.get('render-process-gone')?.[0]?.({}, { reason: 'crashed', exitCode: 1 });
    expect(win.loadURL).toHaveBeenCalledWith('http://127.0.0.1:5173');
  });
});
