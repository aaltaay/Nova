import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildElectronFocusReport,
  displayOrder,
  FOCUS_ELECTRON_HEARTBEAT_MS as ELECTRON_HEARTBEAT_MS,
  FOCUS_SETTLE_MS as ELECTRON_SETTLE_MS,
  startFocusSensor,
} from '../../electron/focusSensor.mjs';
import { FOCUS_ELECTRON_HEARTBEAT_MS, FOCUS_SETTLE_MS } from '../constantGroups/focus';

type Handler = (...args: unknown[]) => void;

function emitter() {
  const handlers = new Map<string, Handler[]>();
  return {
    on: (name: string, fn: Handler) => handlers.set(name, [...(handlers.get(name) ?? []), fn]),
    removeListener: (name: string, fn: Handler) =>
      handlers.set(name, (handlers.get(name) ?? []).filter((h) => h !== fn)),
    emit: (name: string, ...args: unknown[]) => (handlers.get(name) ?? []).forEach((h) => h(...args)),
    count: (name: string) => (handlers.get(name) ?? []).length,
  };
}

const LEFT = { id: 2779098405, label: 'DELL U2720Q', bounds: { x: -3840, y: 0 }, scaleFactor: 1.5 };
const PRIMARY = { id: 1, label: '', bounds: { x: 0, y: 0 }, scaleFactor: 1 };

function fakeScreen(onWhich: Record<string, typeof LEFT>) {
  return {
    ...emitter(),
    getAllDisplays: () => [PRIMARY, LEFT],
    getPrimaryDisplay: () => PRIMARY,
    getDisplayMatching: (bounds: { key: string }) => onWhich[bounds.key],
  };
}

function fakeWindow(url: string, { focused = false, minimized = false, key = 'main' } = {}) {
  return {
    ...emitter(),
    isDestroyed: () => false,
    isFocused: () => focused,
    isMinimized: () => minimized,
    isVisible: () => true,
    getBounds: () => ({ key }),
    webContents: { getURL: () => url },
  };
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Electron focus sensor', () => {
  it('keeps the cadence the renderer constants say', () => {
    expect(ELECTRON_HEARTBEAT_MS).toBe(FOCUS_ELECTRON_HEARTBEAT_MS);
    expect(ELECTRON_SETTLE_MS).toBe(FOCUS_SETTLE_MS);
  });

  it('numbers monitors left to right', () => {
    expect(displayOrder([PRIMARY, LEFT]).map((d) => d.id)).toEqual([LEFT.id, PRIMARY.id]);
  });

  it('names the window in front and the monitor each window is on', () => {
    const report = buildElectronFocusReport({
      windows: [
        fakeWindow('file:///C:/Nova/dist/index.html', { key: 'main' }),
        fakeWindow('file:///C:/Nova/dist/index.html?view=stock&symbol=PFSA', { focused: true, key: 'pop' }),
        fakeWindow('data:text/html,starting'),
      ],
      screen: fakeScreen({ main: PRIMARY, pop: LEFT }),
      reason: 'focus',
    });
    expect(report.role).toBe('electron');
    expect(report.app_focused).toBe(true);
    expect(report.focused_window_id).toBe('trader:PFSA');
    expect(report.windows).toHaveLength(2); // the data: splash is not a desk window
    expect(report.windows[1].display).toEqual({
      id: '2779098405',
      label: 'DELL U2720Q',
      index: 1,
      count: 2,
      primary: false,
      scale_factor: 1.5,
    });
    expect(report.windows[0].display.primary).toBe(true);
  });

  it('says Nova is behind when no window has focus', () => {
    const report = buildElectronFocusReport({
      windows: [fakeWindow('http://127.0.0.1:5173/', { minimized: true })],
      screen: fakeScreen({ main: PRIMARY }),
      reason: 'blur',
    });
    expect(report.app_focused).toBe(false);
    expect(report.focused_window_id).toBeNull();
    expect(report.windows[0]).toMatchObject({ minimized: true, visible: false });
  });

  it('posts on start and once per settled focus switch', async () => {
    vi.useFakeTimers();
    const app = emitter();
    const screen = fakeScreen({ main: PRIMARY });
    const win = fakeWindow('http://127.0.0.1:5173/', { focused: true });
    const fetchImpl = vi.fn(async () => ({ ok: true, status: 200 }));
    const stop = startFocusSensor({
      app,
      BrowserWindow: { getAllWindows: () => [win] },
      screen,
      apiBase: 'http://127.0.0.1:8000',
      apiKey: () => 'k',
      fetchImpl,
    });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, { body: string; headers: Record<string, string> }];
    expect(url).toBe('http://127.0.0.1:8000/sensors/focus');
    expect(JSON.parse(init.body).reason).toBe('start');
    expect(init.headers['X-Nova-Api-Key']).toBe('k');
    await vi.advanceTimersByTimeAsync(0);
    app.emit('browser-window-blur');
    app.emit('browser-window-focus');
    await vi.advanceTimersByTimeAsync(FOCUS_SETTLE_MS);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(JSON.parse((fetchImpl.mock.calls[1] as unknown as [string, { body: string }])[1].body).reason).toBe('focus');
    stop();
    expect(app.count('browser-window-focus')).toBe(0);
  });
});
