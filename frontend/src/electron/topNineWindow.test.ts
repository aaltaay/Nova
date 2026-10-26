import os from 'node:os';
import { describe, expect, it, vi } from 'vitest';
import { isTopNineUrl, openOrFocusTopNineWindow } from '../../electron/topNineWindow.mjs';

function fakeWindowClass() {
  const made: FakeWindow[] = [];
  class FakeWindow {
    opts: Record<string, unknown>;
    destroyed = false;
    minimized = false;
    focus = vi.fn();
    show = vi.fn();
    restore = vi.fn();
    on = vi.fn();
    loadURL = vi.fn(async () => {});
    webContents = {
      on: vi.fn(),
      once: vi.fn(),
      removeListener: vi.fn(),
      setWindowOpenHandler: vi.fn(),
    };
    constructor(opts: Record<string, unknown>) {
      this.opts = opts;
      made.push(this);
    }
    isDestroyed() { return this.destroyed; }
    isMinimized() { return this.minimized; }
    getBounds() { return { x: 0, y: 0, width: 1600, height: 960 }; }
    isMaximized() { return false; }
  }
  return { FakeWindow, made };
}

describe('isTopNineUrl', () => {
  it('takes only a Nova renderer URL on ?view=top9', () => {
    expect(isTopNineUrl('http://127.0.0.1:5173/?view=top9')).toBe(true);
    expect(isTopNineUrl('file:///C:/Nova/dist/index.html?view=top9')).toBe(true);
    expect(isTopNineUrl('http://127.0.0.1:5173/?view=stock&symbol=ZTG')).toBe(false);
    expect(isTopNineUrl('https://example.com/?view=top9#x')).toBe(true);
    expect(isTopNineUrl('chrome-error://chromewebdata/?view=top9')).toBe(false);
    expect(isTopNineUrl('')).toBe(false);
  });
});

describe('openOrFocusTopNineWindow', () => {
  it('opens one window, then focuses it instead of opening another', async () => {
    const { FakeWindow, made } = fakeWindowClass();
    const deps = {
      BrowserWindow: FakeWindow as never,
      userData: os.tmpdir(),
      displays: [{ x: 0, y: 0, width: 1920, height: 1080 }],
      releaseTag: null,
    };
    const url = 'http://127.0.0.1:5173/?view=top9';
    expect(await openOrFocusTopNineWindow(url, { width: 1440 }, deps)).toBe(true);
    expect(made).toHaveLength(1);
    expect(made[0].opts.title).toBe('Nova — Top 9');
    // It opens nothing itself.
    const handler = made[0].webContents.setWindowOpenHandler.mock.calls[0][0] as () => unknown;
    expect(handler()).toEqual({ action: 'deny' });

    made[0].minimized = true;
    expect(await openOrFocusTopNineWindow(url, { width: 1440 }, deps)).toBe(true);
    expect(made).toHaveLength(1);
    expect(made[0].restore).toHaveBeenCalled();
    expect(made[0].focus).toHaveBeenCalled();
    made[0].destroyed = true;
  });

  it('refuses any other URL', async () => {
    const { FakeWindow } = fakeWindowClass();
    await expect(openOrFocusTopNineWindow('http://127.0.0.1:5173/?view=stock&symbol=A', {}, {
      BrowserWindow: FakeWindow as never, userData: os.tmpdir(), displays: [],
    })).rejects.toThrow('Invalid Top 9 URL');
  });
});
