/**
 * This window's performance report (ADR 026): every PERF_REPORT_MS, frame
 * pacing, long animation frames, socket and render tallies, JS heap and DOM
 * size, posted to `POST /api/perf/client` (shape: AGENTS.md sec. 3,
 * "Performance recorder"). Started once from main.tsx; measures only.
 *
 * On the sample desk (`?view=sample`) the window still measures -- so the
 * counters never pile up -- but sends nothing; the sample network gate is the
 * backstop under this check, not the only wall. At most one post is in
 * flight: a stalled API must not have this report queue behind itself and
 * take the connections the desk's own requests need. A failed post never
 * throws into the app and is logged at debug level at most once a minute.
 */
import { PERF_WINDOW_ID_MAIN, perfWindowIdForUrl } from '../../electron/perfWindowId.mjs';
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constantGroups/chart_api';
import {
  PERF_CLIENT_PATH,
  PERF_FAIL_LOG_MS,
  PERF_MAX_BODY_BYTES,
  PERF_MAX_NAME_CHARS,
  PERF_MAX_RENDER_KEYS,
  PERF_MAX_SOCKET_KEYS,
  PERF_REPORT_MS,
  PERF_SCHEMA_VERSION,
} from '../constantGroups/perf';
import { isSampleView } from '../sample_data/sampleNav';
import { startFrameMeter, type FrameMeter, type FrameStats } from './frameMeter';
import { startLongFrames, type LongFrameMeter, type LongFramesReport } from './longFrames';
import { takeCounters, type PerfCounters, type SocketTally } from './perfCounters';

export type PerfRole = 'main' | 'popout' | 'browser' | 'electron';

export interface PerfClientReport {
  schema_version: number;
  window_id: string;
  role: PerfRole;
  visible: boolean | null;
  interval_sec: number;
  ui_tag: string | null;
  frames: FrameStats | null;
  long_frames: LongFramesReport | null;
  sockets: Record<string, SocketTally>;
  renders: Record<string, number>;
  heap_mb: number | null;
  dom_nodes: number | null;
  processes: null;
}

/** The window members the reporter reads; a test passes a stand-in. */
export interface PerfWindow {
  location: Pick<Location, 'href' | 'search'>;
  novaDesktop?: { isDesktop?: boolean };
}

export interface PerfReporterOptions {
  win?: PerfWindow;
  now?: () => number;
  frames?: FrameMeter;
  longFrames?: LongFrameMeter;
}

/** `main` / `popout` inside Electron (by the pop-out's URL), `browser` anywhere else. */
export function perfWindowIdentity(win: PerfWindow): { windowId: string; role: PerfRole } {
  const windowId = perfWindowIdForUrl(win.location.href);
  if (win.novaDesktop?.isDesktop !== true) return { windowId, role: 'browser' };
  return { windowId, role: windowId === PERF_WINDOW_ID_MAIN ? 'main' : 'popout' };
}

function capKeys<T>(src: Record<string, T>, max: number): Record<string, T> {
  const out: Record<string, T> = {};
  let n = 0;
  for (const [name, value] of Object.entries(src)) {
    if (n >= max) break;
    out[name.slice(0, PERF_MAX_NAME_CHARS)] = value;
    n += 1;
  }
  return out;
}

export interface PerfReportParts {
  windowId: string;
  role: PerfRole;
  visible: boolean;
  intervalSec: number;
  uiTag: string | null;
  frames: FrameStats | null;
  longFrames: LongFramesReport | null;
  counters: PerfCounters;
  heapMb: number | null;
  domNodes: number | null;
}

export function buildPerfReport(parts: PerfReportParts): PerfClientReport {
  return {
    schema_version: PERF_SCHEMA_VERSION,
    window_id: parts.windowId,
    role: parts.role,
    visible: parts.visible,
    interval_sec: Math.round(parts.intervalSec * 1000) / 1000,
    ui_tag: parts.uiTag,
    frames: parts.frames,
    long_frames: parts.longFrames,
    sockets: capKeys(parts.counters.sockets, PERF_MAX_SOCKET_KEYS),
    renders: capKeys(parts.counters.renders, PERF_MAX_RENDER_KEYS),
    heap_mb: parts.heapMb,
    dom_nodes: parts.domNodes,
    processes: null,
  };
}

function uiTag(): string | null {
  return typeof __NOVA_RELEASE_TAG__ === 'string' && __NOVA_RELEASE_TAG__ ? __NOVA_RELEASE_TAG__ : null;
}

function heapMb(): number | null {
  if (typeof performance === 'undefined') return null;
  const used = (performance as Performance & { memory?: { usedJSHeapSize?: number } }).memory
    ?.usedJSHeapSize;
  return typeof used === 'number' ? Math.round(used / 1e5) / 10 : null;
}

function domNodes(): number | null {
  return typeof document === 'undefined' ? null : document.getElementsByTagName('*').length;
}

/** A post still unanswered when the next report is due is abandoned. */
function postTimeout(): AbortSignal | undefined {
  return typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(PERF_REPORT_MS)
    : undefined;
}

function isVisible(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'visible';
}

let running: (() => void) | null = null;

/** Start this window's report loop once; later calls return the same stop. */
export function startPerfReporter(options: PerfReporterOptions = {}): () => void {
  if (running) return running;
  const win = options.win ?? window;
  const now = options.now ?? (() => performance.now());
  const frames = options.frames ?? startFrameMeter();
  const longFrames = options.longFrames ?? startLongFrames();
  let lastTs = now();
  let lastFailLog = -Infinity;
  let inFlight = false;

  const noteFailure = (why: unknown) => {
    const t = now();
    if (t - lastFailLog < PERF_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[Nova] perf report not delivered', why);
  };

  const send = (report: PerfClientReport) => {
    const body = JSON.stringify(report);
    if (new TextEncoder().encode(body).length > PERF_MAX_BODY_BYTES) {
      noteFailure(`report over ${PERF_MAX_BODY_BYTES} bytes`);
      return;
    }
    if (inFlight) {
      noteFailure('previous report still in flight');
      return;
    }
    inFlight = true;
    try {
      void novaFetch(`${API_BASE_URL}${PERF_CLIENT_PATH}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true,
        signal: postTimeout(),
      })
        .then((res) => {
          if (!res.ok) noteFailure(`HTTP ${res.status}`);
        }, noteFailure)
        .finally(() => {
          inFlight = false;
        });
    } catch (err) {
      inFlight = false;
      noteFailure(err);
    }
  };

  const tick = () => {
    const t = now();
    const intervalSec = (t - lastTs) / 1000;
    lastTs = t;
    // Take every tally even when nothing is sent, so none carries into the next report.
    const counters = takeCounters();
    const frameStats = frames.take();
    const longFrameStats = longFrames.take();
    if (isSampleView(win.location.search)) return;
    const { windowId, role } = perfWindowIdentity(win);
    send(
      buildPerfReport({
        windowId,
        role,
        visible: isVisible(),
        intervalSec,
        uiTag: uiTag(),
        frames: frameStats,
        longFrames: longFrameStats,
        counters,
        heapMb: heapMb(),
        domNodes: domNodes(),
      }),
    );
  };

  const timer = setInterval(tick, PERF_REPORT_MS);
  running = () => {
    clearInterval(timer);
    frames.stop();
    longFrames.stop();
    running = null;
  };
  return running;
}
