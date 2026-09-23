/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  PERF_CLIENT_PATH,
  PERF_MAX_RENDER_KEYS,
  PERF_MAX_SOCKET_KEYS,
  PERF_REPORT_MS,
  PERF_SCHEMA_VERSION,
} from '../constantGroups/perf';
import type { FrameMeter } from './frameMeter';
import type { LongFrameMeter } from './longFrames';
import { countRender, countSocketMessage, resetPerfCountersForTests } from './perfCounters';
import {
  buildPerfReport,
  perfWindowIdentity,
  startPerfReporter,
  type PerfWindow,
} from './perfReporter';

const REPORT_KEYS = [
  'dom_nodes',
  'frames',
  'heap_mb',
  'interval_sec',
  'long_frames',
  'processes',
  'renders',
  'role',
  'schema_version',
  'sockets',
  'ui_tag',
  'visible',
  'window_id',
];

const liveWin = (search = '', desktop = false): PerfWindow => ({
  location: { href: `http://127.0.0.1:5173/${search}`, search },
  novaDesktop: desktop ? { isDesktop: true } : undefined,
});

const frames: FrameMeter = { take: () => ({ count: 300, slow: 4, p95_ms: 18.2 }), stop: () => {} };
const longFrames: LongFrameMeter = {
  take: () => ({ count: 1, blocking_ms: 30, max_ms: 80, top: [{ source: 'f @ a.js', invoker: 'x', ms: 70 }] }),
  stop: () => {},
};

let fetchSpy: ReturnType<typeof vi.fn>;
let stop: (() => void) | null = null;

function start(win: PerfWindow): void {
  let t = 0;
  stop = startPerfReporter({
    win,
    frames,
    longFrames,
    now: () => {
      t += PERF_REPORT_MS;
      return t;
    },
  });
}

function posted(): Array<{ url: string; init: RequestInit; body: Record<string, unknown> }> {
  return fetchSpy.mock.calls.map(([url, init]) => ({
    url: String(url),
    init: init as RequestInit,
    body: JSON.parse(String((init as RequestInit).body)),
  }));
}

beforeEach(() => {
  vi.useFakeTimers();
  fetchSpy = vi.fn(async () => new Response('{"ok":true}', { status: 200 }));
  vi.stubGlobal('fetch', fetchSpy);
  resetPerfCountersForTests();
});

afterEach(() => {
  stop?.();
  stop = null;
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('perf window identity', () => {
  it('names the host window main and a Trader pop-out by its symbol', () => {
    expect(perfWindowIdentity(liveWin('', true))).toEqual({ windowId: 'main', role: 'main' });
    expect(perfWindowIdentity(liveWin('?view=stock&symbol=grml', true))).toEqual({
      windowId: 'trader:GRML',
      role: 'popout',
    });
    expect(perfWindowIdentity(liveWin('?view=stock&symbol=BRK/B', true)).windowId).toBe('trader:BRK_B');
    expect(perfWindowIdentity(liveWin('?view=stock&symbol=GRML'))).toEqual({
      windowId: 'trader:GRML',
      role: 'browser',
    });
    expect(perfWindowIdentity(liveWin())).toEqual({ windowId: 'main', role: 'browser' });
  });
});

describe('perf report', () => {
  it('posts the contract shape to /api/perf/client every interval', async () => {
    countSocketMessage('tape', 120);
    countRender('DepthLadder');
    start(liveWin('', true));
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS);

    const [report] = posted();
    expect(report.url.endsWith(PERF_CLIENT_PATH)).toBe(true);
    expect(report.init.method).toBe('POST');
    expect(report.init.keepalive).toBe(true);
    expect(Object.keys(report.body).sort()).toEqual(REPORT_KEYS);
    expect(report.body).toMatchObject({
      schema_version: PERF_SCHEMA_VERSION,
      window_id: 'main',
      role: 'main',
      interval_sec: PERF_REPORT_MS / 1000,
      frames: { count: 300, slow: 4, p95_ms: 18.2 },
      long_frames: { count: 1, blocking_ms: 30, max_ms: 80 },
      sockets: { tape: { messages: 1, bytes: 120 } },
      renders: { DepthLadder: 1 },
      processes: null,
    });
    expect(typeof report.body.visible).toBe('boolean');
    expect(typeof report.body.dom_nodes).toBe('number');
    expect(report.body.heap_mb === null || typeof report.body.heap_mb === 'number').toBe(true);

    // The next report starts from zero.
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS);
    expect(posted()[1].body).toMatchObject({ sockets: {}, renders: {} });
  });

  it('caps sockets and renders at their key limits', () => {
    const sockets = Object.fromEntries(
      Array.from({ length: PERF_MAX_SOCKET_KEYS + 10 }, (_, i) => [`s${i}`, { messages: 1, bytes: 1 }]),
    );
    const renders = Object.fromEntries(Array.from({ length: PERF_MAX_RENDER_KEYS + 10 }, (_, i) => [`R${i}`, 1]));
    const report = buildPerfReport({
      windowId: 'main',
      role: 'browser',
      visible: false,
      intervalSec: 5.0004,
      uiTag: null,
      frames: null,
      longFrames: null,
      counters: { sockets, renders },
      heapMb: null,
      domNodes: null,
    });
    expect(Object.keys(report.sockets)).toHaveLength(PERF_MAX_SOCKET_KEYS);
    expect(Object.keys(report.renders)).toHaveLength(PERF_MAX_RENDER_KEYS);
    expect(report.interval_sec).toBe(5);
    expect(report.frames).toBeNull();
    expect(report.processes).toBeNull();
  });

  it('sends nothing on the sample desk', async () => {
    countSocketMessage('tape', 1);
    start(liveWin('?view=sample&symbol=GRML'));
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS * 3);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('starts once however often it is called', async () => {
    start(liveWin());
    const again = startPerfReporter({ win: liveWin(), frames, longFrames });
    expect(again).toBe(stop);
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('a failed post never throws and is logged at most once a minute', async () => {
    fetchSpy.mockRejectedValue(new TypeError('Failed to fetch'));
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
    start(liveWin());
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS * 4);
    expect(fetchSpy).toHaveBeenCalledTimes(4);
    expect(debug).toHaveBeenCalledTimes(1);
  });

  it('a refused post (HTTP 4xx) is a logged failure, not an exception', async () => {
    fetchSpy.mockResolvedValue(new Response('{}', { status: 422 }));
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => {});
    start(liveWin());
    await vi.advanceTimersByTimeAsync(PERF_REPORT_MS);
    expect(debug).toHaveBeenCalledWith('[Nova] perf report not delivered', 'HTTP 422');
  });
});
