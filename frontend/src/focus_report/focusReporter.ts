/**
 * This window's focus report (ADR 031): which page and symbol it shows, whether
 * Windows has it in front, and when the operator last clicked or typed in it --
 * posted to `POST /sensors/focus` on every change and every FOCUS_HEARTBEAT_MS,
 * so an agent or a bot reads the operator's focus instead of guessing
 * (`GET /sensors/focus`). Started once from main.tsx; the app shell feeds it the
 * view through `setFocusView`. The sample desk sends nothing. At most one post
 * is in flight; a change that arrives meanwhile is sent when it returns.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constantGroups/chart_api';
import {
  FOCUS_FAIL_LOG_MS,
  FOCUS_HEARTBEAT_MS,
  FOCUS_INPUT_REPORT_MIN_MS,
  FOCUS_MAX_TABS,
  FOCUS_REPORT_PATH,
  FOCUS_SCHEMA_VERSION,
  FOCUS_SETTLE_MS,
} from '../constantGroups/focus';
import { perfWindowIdentity, type PerfRole, type PerfWindow } from '../perf/perfReporter';
import { isSampleView } from '../sample_data/sampleNav';

export type FocusPage = 'trader' | 'desk' | 'scanner' | 'account' | 'bots' | 'records';
export type FocusSymbolSource = 'trader_tab' | 'desk_board' | 'scanner_row';
export type FocusReason = 'start' | 'focus' | 'blur' | 'visibility' | 'page' | 'symbol' | 'input' | 'heartbeat';

export interface FocusView {
  page: FocusPage | null;
  /** The scanner tab on the Scanner page, else null. */
  tab: string | null;
  symbol: string | null;
  symbolSource: FocusSymbolSource | null;
  traderTabs: string[];
}

export interface FocusReport {
  schema_version: number;
  role: Exclude<PerfRole, 'electron'>;
  window_id: string;
  instance_id: string;
  focused: boolean;
  visible: boolean;
  page: FocusPage | null;
  tab: string | null;
  symbol: string | null;
  symbol_source: FocusSymbolSource | null;
  trader_tabs: string[];
  /** Epoch seconds of the last click / keypress / wheel in this window. */
  last_input_ts: number | null;
  reason: FocusReason;
  ui_tag: string | null;
}

export const EMPTY_FOCUS_VIEW: FocusView = { page: null, tab: null, symbol: null, symbolSource: null, traderTabs: [] };

/** The window members the reporter reads; a test passes a stand-in. */
export interface FocusWindow extends PerfWindow {
  addEventListener: Window['addEventListener'];
  removeEventListener: Window['removeEventListener'];
}

export interface FocusDocument {
  hasFocus(): boolean;
  visibilityState: DocumentVisibilityState;
  addEventListener: Document['addEventListener'];
  removeEventListener: Document['removeEventListener'];
}

export interface FocusReporterOptions {
  win?: FocusWindow;
  doc?: FocusDocument;
  /** Wall clock in ms (the report carries epoch seconds). */
  now?: () => number;
  post?: (body: string) => Promise<{ ok: boolean; status: number }>;
}

export function sameView(a: FocusView, b: FocusView): boolean {
  return (
    a.page === b.page &&
    a.tab === b.tab &&
    a.symbol === b.symbol &&
    a.symbolSource === b.symbolSource &&
    a.traderTabs.join(',') === b.traderTabs.join(',')
  );
}

export function buildFocusReport(parts: {
  windowId: string;
  role: FocusReport['role'];
  instanceId: string;
  focused: boolean;
  visible: boolean;
  view: FocusView;
  lastInputMs: number | null;
  reason: FocusReason;
  uiTag: string | null;
}): FocusReport {
  return {
    schema_version: FOCUS_SCHEMA_VERSION,
    role: parts.role,
    window_id: parts.windowId,
    instance_id: parts.instanceId,
    focused: parts.focused,
    visible: parts.visible,
    page: parts.view.page,
    tab: parts.view.tab,
    symbol: parts.view.symbol,
    symbol_source: parts.view.symbolSource,
    trader_tabs: parts.view.traderTabs.slice(0, FOCUS_MAX_TABS),
    last_input_ts: parts.lastInputMs == null ? null : Math.round(parts.lastInputMs) / 1000,
    reason: parts.reason,
    ui_tag: parts.uiTag,
  };
}

function uiTag(): string | null {
  return typeof __NOVA_RELEASE_TAG__ === 'string' && __NOVA_RELEASE_TAG__ ? __NOVA_RELEASE_TAG__ : null;
}

function newInstanceId(): string {
  const raw =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
  return raw.replace(/[^A-Za-z0-9_.:-]/g, '').slice(0, 64);
}

function defaultPost(body: string): Promise<{ ok: boolean; status: number }> {
  const signal =
    typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function'
      ? AbortSignal.timeout(FOCUS_HEARTBEAT_MS)
      : undefined;
  return novaFetch(`${API_BASE_URL}${FOCUS_REPORT_PATH}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
    signal,
  });
}

let view: FocusView = EMPTY_FOCUS_VIEW;
let onViewChange: ((reason: FocusReason) => void) | null = null;
let running: (() => void) | null = null;

/** The app shell's view of this window; a change is reported once it settles. */
export function setFocusView(next: FocusView): void {
  if (sameView(view, next)) return;
  const reason: FocusReason = next.page !== view.page ? 'page' : 'symbol';
  view = next;
  onViewChange?.(reason);
}

/** Start this window's focus reports once; later calls return the same stop. */
export function startFocusReporter(options: FocusReporterOptions = {}): () => void {
  if (running) return running;
  const win = options.win ?? window;
  const doc = options.doc ?? document;
  const now = options.now ?? (() => Date.now());
  const post = options.post ?? defaultPost;
  const instanceId = newInstanceId();
  let lastInputMs: number | null = null;
  let lastSentMs = -Infinity;
  let lastFailLog = -Infinity;
  let inFlight = false;
  let queued: FocusReason | null = null;
  let settleTimer: ReturnType<typeof setTimeout> | null = null;
  let settleReason: FocusReason | null = null;

  const noteFailure = (why: unknown) => {
    const t = now();
    if (t - lastFailLog < FOCUS_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[Nova] focus report not delivered', why);
  };

  const report = (reason: FocusReason) => {
    if (isSampleView(win.location.search)) return;
    if (inFlight) {
      // A change outranks a heartbeat or an input; whatever waits is sent with the view as it is then.
      if (queued === null || queued === 'heartbeat' || queued === 'input') queued = reason;
      return;
    }
    const { windowId, role } = perfWindowIdentity(win);
    const body = JSON.stringify(
      buildFocusReport({
        windowId,
        role: role === 'electron' ? 'main' : role,
        instanceId,
        focused: doc.hasFocus(),
        visible: doc.visibilityState === 'visible',
        view,
        lastInputMs,
        reason,
        uiTag: uiTag(),
      }),
    );
    inFlight = true;
    lastSentMs = now();
    let sent: Promise<{ ok: boolean; status: number }>;
    try {
      sent = post(body);
    } catch (err) {
      inFlight = false;
      noteFailure(err);
      return;
    }
    void sent
      .then((res) => {
        if (!res.ok) noteFailure(`HTTP ${res.status}`);
      }, noteFailure)
      .finally(() => {
        inFlight = false;
        const next = queued;
        queued = null;
        if (next) report(next);
      });
  };

  const settle = (reason: FocusReason) => {
    if (settleReason !== 'page') settleReason = reason;
    if (settleTimer) return;
    settleTimer = setTimeout(() => {
      settleTimer = null;
      const r = settleReason ?? reason;
      settleReason = null;
      report(r);
    }, FOCUS_SETTLE_MS);
  };

  const onFocus = () => report('focus');
  const onBlur = () => report('blur');
  const onVisibility = () => report('visibility');
  const onInput = () => {
    lastInputMs = now();
    if (lastInputMs - lastSentMs >= FOCUS_INPUT_REPORT_MIN_MS) report('input');
  };
  const inputOpts: AddEventListenerOptions = { capture: true, passive: true };

  win.addEventListener('focus', onFocus);
  win.addEventListener('blur', onBlur);
  doc.addEventListener('visibilitychange', onVisibility);
  for (const type of ['pointerdown', 'keydown', 'wheel'] as const) win.addEventListener(type, onInput, inputOpts);
  onViewChange = settle;
  const timer = setInterval(() => report('heartbeat'), FOCUS_HEARTBEAT_MS);
  report('start');

  running = () => {
    clearInterval(timer);
    if (settleTimer) clearTimeout(settleTimer);
    win.removeEventListener('focus', onFocus);
    win.removeEventListener('blur', onBlur);
    doc.removeEventListener('visibilitychange', onVisibility);
    for (const type of ['pointerdown', 'keydown', 'wheel'] as const) {
      win.removeEventListener(type, onInput, inputOpts);
    }
    onViewChange = null;
    running = null;
  };
  return running;
}

export function resetFocusReporterForTests(): void {
  running?.();
  view = EMPTY_FOCUS_VIEW;
}
