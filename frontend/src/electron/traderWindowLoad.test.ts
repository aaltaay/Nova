import { describe, expect, it, vi } from 'vitest';
import {
  isAllowedRendererUrl,
  loadTraderWindow,
} from '../../electron/traderWindowLoad.mjs';

describe('isAllowedRendererUrl', () => {
  it('refuses chrome-error and empty URLs', () => {
    expect(isAllowedRendererUrl('')).toBe(false);
    expect(isAllowedRendererUrl('chrome-error://chromewebdata/')).toBe(false);
    expect(isAllowedRendererUrl('about:blank')).toBe(false);
  });

  it('allows Vite http and packaged file URLs', () => {
    expect(isAllowedRendererUrl('http://127.0.0.1:5173/')).toBe(true);
    expect(isAllowedRendererUrl('file:///C:/Nova/dist/index.html')).toBe(true);
  });

  it('requires view=stock and a symbol for Trader windows', () => {
    expect(
      isAllowedRendererUrl('http://127.0.0.1:5173/', { requireStockView: true }),
    ).toBe(false);
    expect(
      isAllowedRendererUrl('http://127.0.0.1:5173/?view=stock', {
        requireStockView: true,
      }),
    ).toBe(false);
    expect(
      isAllowedRendererUrl('http://127.0.0.1:5173/?view=stock&symbol=SPY', {
        requireStockView: true,
      }),
    ).toBe(true);
    expect(
      isAllowedRendererUrl('file:///C:/Nova/dist/index.html?view=stock&symbol=QQQ', {
        requireStockView: true,
      }),
    ).toBe(true);
  });
});

describe('loadTraderWindow', () => {
  function mockWin(loadImpl: () => Promise<void>) {
    const listeners = new Map<string, ((...args: unknown[]) => void)[]>();
    const win = {
      loadURL: vi.fn(loadImpl),
      show: vi.fn(),
      focus: vi.fn(),
      close: vi.fn(),
      isDestroyed: vi.fn(() => false),
      webContents: {
        once: vi.fn((event: string, fn: (...args: unknown[]) => void) => {
          const list = listeners.get(event) ?? [];
          list.push(fn);
          listeners.set(event, list);
        }),
        removeListener: vi.fn((event: string, fn: (...args: unknown[]) => void) => {
          const list = (listeners.get(event) ?? []).filter((x) => x !== fn);
          listeners.set(event, list);
        }),
      },
    };
    return { win, listeners };
  }

  it('shows the window only after loadURL resolves', async () => {
    const { win } = mockWin(() => Promise.resolve());
    await expect(loadTraderWindow(win, 'http://127.0.0.1:5173/?view=stock&symbol=SPY')).resolves.toBe(
      true,
    );
    expect(win.show).toHaveBeenCalledOnce();
    expect(win.focus).toHaveBeenCalledOnce();
    expect(win.close).not.toHaveBeenCalled();
  });

  it('closes a chrome-error load so the blank shell does not stay focused', async () => {
    const { win } = mockWin(() => Promise.reject(new Error('ERR_FAILED')));
    await expect(loadTraderWindow(win, 'chrome-error://chromewebdata/')).resolves.toBe(false);
    expect(win.show).not.toHaveBeenCalled();
    expect(win.close).toHaveBeenCalledOnce();
  });
});
