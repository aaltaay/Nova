import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  buildElectronPerfReport,
  PERF_ELECTRON_REPORT_MS as ELECTRON_REPORT_MS,
  startPerfMetrics,
  windowIdsByPid,
} from '../../electron/perfMetrics.mjs';
import { PERF_ELECTRON_REPORT_MS } from '../constantGroups/perf';

function fakeWindow(pid: number, url: string, destroyed = false) {
  return {
    isDestroyed: () => destroyed,
    webContents: { getOSProcessId: () => pid, getURL: () => url },
  };
}

const METRICS = [
  { pid: 100, type: 'Browser', cpu: { percentCPUUsage: 3.14 }, memory: { workingSetSize: 204_800 } },
  { pid: 200, type: 'Tab', cpu: { percentCPUUsage: 41.26 }, memory: { workingSetSize: 512_000 } },
  { pid: 300, type: 'Tab', cpu: { percentCPUUsage: 12 }, memory: { workingSetSize: 307_200 } },
  { pid: 400, type: 'GPU', cpu: { percentCPUUsage: 8 }, memory: { workingSetSize: 102_400 } },
];

const WINDOWS = [
  fakeWindow(200, 'file:///C:/Nova/dist/index.html'),
  fakeWindow(300, 'file:///C:/Nova/dist/index.html?view=stock&symbol=GRML'),
  fakeWindow(999, 'http://127.0.0.1:5173/', true),
];

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Electron perf metrics', () => {
  it('reports on the same cadence as the renderer constants say', () => {
    expect(ELECTRON_REPORT_MS).toBe(PERF_ELECTRON_REPORT_MS);
  });

  it('names each renderer process by the window_id its window reports', () => {
    expect(Object.fromEntries(windowIdsByPid(WINDOWS))).toEqual({ 200: 'main', 300: 'trader:GRML' });
  });

  it('builds the role=electron report with one row per process', () => {
    const report = buildElectronPerfReport({ metrics: METRICS, windows: WINDOWS, intervalSec: 5.0001, uiTag: 'v512' });
    expect(report).toMatchObject({
      schema_version: 1,
      window_id: 'electron-main',
      role: 'electron',
      visible: null,
      interval_sec: 5,
      ui_tag: 'v512',
      frames: null,
      long_frames: null,
      sockets: {},
      renders: {},
      heap_mb: null,
      dom_nodes: null,
    });
    expect(report.processes).toEqual([
      { type: 'Browser', window_id: null, pid: 100, cpu_pct: 3.1, working_set_mb: 200 },
      { type: 'Tab', window_id: 'main', pid: 200, cpu_pct: 41.3, working_set_mb: 500 },
      { type: 'Tab', window_id: 'trader:GRML', pid: 300, cpu_pct: 12, working_set_mb: 300 },
      { type: 'GPU', window_id: null, pid: 400, cpu_pct: 8, working_set_mb: 100 },
    ]);
  });

  it('posts every interval with the API key, and a failed post never throws', async () => {
    vi.useFakeTimers();
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('connect ECONNREFUSED');
    });
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
    const stop = startPerfMetrics({
      app: { getAppMetrics: () => METRICS },
      BrowserWindow: { getAllWindows: () => WINDOWS },
      apiBase: 'http://127.0.0.1:8000',
      apiKey: () => 'k',
      fetchImpl,
    });
    await vi.advanceTimersByTimeAsync(ELECTRON_REPORT_MS * 3);
    stop();
    expect(fetchImpl).toHaveBeenCalledTimes(3);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://127.0.0.1:8000/api/perf/client');
    expect((init.headers as Record<string, string>)['X-Nova-Api-Key']).toBe('k');
    expect(JSON.parse(String(init.body)).processes).toHaveLength(4);
    expect(debug).toHaveBeenCalledTimes(1);
  });
});
