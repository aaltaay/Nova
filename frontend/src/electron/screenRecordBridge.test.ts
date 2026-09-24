/**
 * The screen recording's status out of the main process (ADR 035): every desk
 * window hears it, the hidden recorder and the starting splash do not, and the
 * backend gets it on every state change and on a steady beat.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SCREEN_RECORD_SUBSCRIBE_CHANNEL,
  SCREEN_RECORD_VIEW_CHANNEL,
  createScreenRecordBridge,
} from '../../electron/screenRecordBridge.mjs';
import { perfWindowIdForUrl, PERF_WINDOW_ID_SCREEN_RECORDER } from '../../electron/perfWindowId.mjs';
import { buildElectronFocusReport } from '../../electron/focusSensor.mjs';

type Sent = [string, unknown];

function fakeWindow(url: string) {
  const sent: Sent[] = [];
  return {
    sent,
    isDestroyed: () => false,
    isFocused: () => false,
    isMinimized: () => false,
    isVisible: () => false,
    getBounds: () => ({ x: 0, y: 0, width: 10, height: 10 }),
    webContents: {
      isDestroyed: () => false,
      getURL: () => url,
      send: (channel: string, view: unknown) => sent.push([channel, view]),
    },
  };
}

const RECORDER_URL = 'file:///C:/Program%20Files/Nova/resources/app.asar/electron/screenRecorder.html';

function world() {
  const desk = fakeWindow('http://127.0.0.1:5173/');
  const trader = fakeWindow('http://127.0.0.1:5173/?view=stock&symbol=GRML');
  const splash = fakeWindow('data:text/html,starting');
  const recorder = fakeWindow(RECORDER_URL);
  const handlers = new Map<string, () => unknown>();
  const ipcMain = { handle: (channel: string, fn: () => unknown) => handlers.set(channel, fn), removeHandler: vi.fn() };
  const fetchImpl = vi.fn(async (_url: string, _init: RequestInit) => ({ ok: true, status: 200 }));
  const bridge = createScreenRecordBridge({
    ipcMain,
    BrowserWindow: { getAllWindows: () => [desk, trader, splash, recorder] },
    isRecorderWindow: (w: unknown) => w === recorder,
    apiBase: 'http://127.0.0.1:8000',
    apiKey: () => 'k3y',
    fetchImpl,
    intervalMs: 10_000,
  });
  return { desk, trader, splash, recorder, handlers, fetchImpl, bridge };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe('createScreenRecordBridge', () => {
  it('sends each view to every desk window, never to the recorder or the splash', () => {
    const w = world();
    const view = { schema_version: 1, state: 'recording' };
    w.bridge.publish(view);
    expect(w.desk.sent).toEqual([[SCREEN_RECORD_VIEW_CHANNEL, view]]);
    expect(w.trader.sent).toEqual([[SCREEN_RECORD_VIEW_CHANNEL, view]]);
    expect(w.splash.sent).toEqual([]);
    expect(w.recorder.sent).toEqual([]);
    expect(w.handlers.get(SCREEN_RECORD_SUBSCRIBE_CHANNEL)?.()).toBe(view);
  });

  it('posts to the backend at once on a state change, then on its beat', async () => {
    const w = world();
    w.bridge.publish({ state: 'starting' });
    await vi.advanceTimersByTimeAsync(0);
    w.bridge.publish({ state: 'recording' });
    await vi.advanceTimersByTimeAsync(0);
    w.bridge.publish({ state: 'recording', restarts: 0 });
    expect(w.fetchImpl).toHaveBeenCalledTimes(2);
    const [url, init] = w.fetchImpl.mock.calls[1];
    expect(url).toBe('http://127.0.0.1:8000/api/screen-record');
    expect((init.headers as Record<string, string>)['X-Nova-Api-Key']).toBe('k3y');
    expect(JSON.parse(String(init.body))).toEqual({ state: 'recording' });
    await vi.advanceTimersByTimeAsync(10_000);
    expect(w.fetchImpl).toHaveBeenCalledTimes(3);
  });

  it('never throws when the backend is down', async () => {
    const w = world();
    w.fetchImpl.mockRejectedValueOnce(new Error('ECONNREFUSED'));
    expect(() => w.bridge.publish({ state: 'failed' })).not.toThrow();
    await vi.advanceTimersByTimeAsync(0);
  });
});

describe('the hidden recorder window', () => {
  it('has its own perf window id and is left out of the focus report', () => {
    expect(perfWindowIdForUrl(RECORDER_URL)).toBe(PERF_WINDOW_ID_SCREEN_RECORDER);
    expect(perfWindowIdForUrl('http://127.0.0.1:5173/screenRecorder.html')).toBe('main');
    const w = world();
    const screen = {
      getAllDisplays: () => [{ id: 1, label: '', bounds: { x: 0, y: 0 }, scaleFactor: 1 }],
      getPrimaryDisplay: () => ({ id: 1 }),
      getDisplayMatching: () => ({ id: 1, label: '', bounds: { x: 0, y: 0 }, scaleFactor: 1 }),
    };
    const report = buildElectronFocusReport({ windows: [w.desk, w.recorder], screen, reason: 'heartbeat' });
    expect(report.windows.map((r: { window_id: string }) => r.window_id)).toEqual(['main']);
  });
});
