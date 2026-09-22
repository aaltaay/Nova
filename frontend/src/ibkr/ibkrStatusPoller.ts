/**
 * Single /api/ibkr/status source for the desk.
 *
 * Every useIbkrStatus() subscriber reads this snapshot. One interval, one
 * in-flight fetch. A failed poll marks stale, forces connected=false so the
 * Desk chip / trading gates cannot stay green, and withdraws the recording
 * claims (QA C23): the header REC chip already hid on a stale status, while
 * the rail, Desk and Records kept "Recording: GDC, IMCC" from a snapshot
 * nobody could read any more. After N misses the stale snapshot persists.
 *
 * Every payload goes through normalizeIbkrStatus (QA C1 / C4). On the sample
 * route (V4) the snapshot is the Nova Marketing Sample Data status and no
 * request is made.
 */
import {
  API_BASE_URL,
  IBKR_STATUS_POLL_MS,
  IBKR_STATUS_STALE_AFTER_MISSES,
} from '../constants';
import { isSampleView } from '../sample_data/sampleNav';
import { SAMPLE_IBKR_STATUS } from '../sample_data/sampleStatus';
import { readLastIbkrStatus, writeLastIbkrStatus } from './ibkrStatusCache';
import { normalizeIbkrStatus } from './ibkrStatusNormalize';
import type { IbkrStatus } from './types';

export type IbkrClientStatus = IbkrStatus & {
  /** False until a poll finishes or this tab already has last-good status. */
  clientReady: boolean;
  /** Successful in-memory read only; persisted cache cannot attest freshness. */
  lastSuccessAt?: number | null;
  /** True after consecutive /api/ibkr/status failures. */
  stale: boolean;
  /** epoch ms of the first consecutive miss; null when fresh. */
  staleSince: number | null;
  /**
   * Why the last poll failed ("HTTP 500", "unreadable response", "no answer"),
   * null after a success -- so a failed status route is never read as a
   * Gateway that went down (QA C58).
   */
  statusError?: string | null;
};

/** The present-tense recording claims a failed poll withdraws (C23). */
const RECORDING_WITHDRAWN: Partial<IbkrStatus> = {
  capture: false,
  recording: false,
  capture_symbol: null,
  capture_symbols: [],
  capture_sessions: [],
  capture_resume: [],
};

export const DEFAULT_IBKR_STATUS: IbkrStatus = {
  enabled: false,
  connected: false,
  transport_connected: false,
  session_reason: 'disabled',
  mode: 'disconnected',
  orders_enabled: false,
  short_enabled: false,
  spend_status: 'locked',
  trading_allowed: false,
  trading_allowed_reason: 'IBKR not connected',
  market_data_type: null,
  market_data_delayed: false,
};

function hydrate(): IbkrClientStatus {
  const last = normalizeIbkrStatus(readLastIbkrStatus());
  if (last) {
    return { ...last, clientReady: true, stale: false, staleSince: null, lastSuccessAt: null };
  }
  return { ...DEFAULT_IBKR_STATUS, clientReady: false, stale: false, staleSince: null, lastSuccessAt: null };
}

type Listener = () => void;

let snapshot: IbkrClientStatus = hydrate();
const listeners = new Set<Listener>();
let subscriberCount = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inflight = false;
let pending = false;
let misses = 0;
let fetchImpl: typeof fetch = (...args) => fetch(...args);
let nowImpl = () => Date.now();
let routeIsSample = false;
let routeListening = false;

function emit(): void {
  listeners.forEach((fn) => fn());
}

/** Entering or leaving the sample desk swaps the snapshot at once (V4). */
function onRouteChange(): void {
  const sample = isSampleView();
  if (sample === routeIsSample) return;
  routeIsSample = sample;
  emit();
  if (!sample) void pollIbkrStatusOnce();
}

function listenRoute(on: boolean): void {
  if (typeof window === 'undefined' || on === routeListening) return;
  routeListening = on;
  routeIsSample = isSampleView();
  if (on) window.addEventListener('popstate', onRouteChange);
  else window.removeEventListener('popstate', onRouteChange);
}

function applySuccess(next: IbkrStatus): void {
  misses = 0;
  writeLastIbkrStatus(next);
  snapshot = {
    ...next,
    clientReady: true,
    stale: false,
    staleSince: null,
    lastSuccessAt: nowImpl(),
    statusError: null,
  };
  emit();
}

function applyFailure(reason: string): void {
  misses += 1;
  const staleSince = snapshot.staleSince ?? nowImpl();
  const next: IbkrClientStatus = {
    ...snapshot,
    ...RECORDING_WITHDRAWN,
    connected: false,
    transport_connected: false,
    clientReady: true,
    stale: true,
    staleSince,
    statusError: reason,
  };
  if (misses >= IBKR_STATUS_STALE_AFTER_MISSES) {
    writeLastIbkrStatus(next);
  }
  snapshot = next;
  emit();
}

async function readStatusBody(res: Response): Promise<IbkrStatus | null> {
  try {
    return normalizeIbkrStatus(await res.json());
  } catch (err) {
    console.warn('[Nova] /api/ibkr/status answered an unreadable body', err);
    return null;
  }
}

export async function pollIbkrStatusOnce(): Promise<void> {
  if (isSampleView()) return;
  if (inflight) {
    pending = true;
    return;
  }
  inflight = true;
  try {
    const res = await fetchImpl(`${API_BASE_URL}/api/ibkr/status`);
    if (res.ok) {
      const body = await readStatusBody(res);
      if (body) applySuccess(body);
      else applyFailure('unreadable response');
    } else {
      applyFailure(res.status ? `HTTP ${res.status}` : 'HTTP error');
    }
  } catch (err) {
    // Once per outage, not every poll: the stale chip carries the rest.
    if (misses === 0) console.warn('[Nova] /api/ibkr/status poll failed', err);
    applyFailure('no answer');
  } finally {
    inflight = false;
    if (pending) {
      pending = false;
      void pollIbkrStatusOnce();
    }
  }
}

function startPolling(): void {
  if (timer != null) return;
  void pollIbkrStatusOnce();
  timer = setInterval(() => {
    void pollIbkrStatusOnce();
  }, IBKR_STATUS_POLL_MS);
}

function stopPolling(): void {
  if (timer != null) {
    clearInterval(timer);
    timer = null;
  }
}

/** The desk's status; on ?view=sample, the sample status (V4). */
export function getIbkrStatusSnapshot(): IbkrClientStatus {
  return isSampleView() ? SAMPLE_IBKR_STATUS : snapshot;
}

export function subscribeIbkrStatus(listener: Listener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    listenRoute(true);
    startPolling();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    if (subscriberCount === 0) {
      stopPolling();
      listenRoute(false);
    }
  };
}

export function refreshIbkrStatusNow(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('ibkr-status-refresh'));
  }
  void pollIbkrStatusOnce();
}

export function _resetIbkrStatusPollerForTests(): void {
  stopPolling();
  listenRoute(false);
  listeners.clear();
  subscriberCount = 0;
  inflight = false;
  pending = false;
  misses = 0;
  fetchImpl = (...args) => fetch(...args);
  nowImpl = () => Date.now();
  snapshot = hydrate();
}

export function _setIbkrStatusPollerFetchForTests(fn: typeof fetch): void {
  fetchImpl = fn;
}

export function _setIbkrStatusPollerNowForTests(fn: () => number): void {
  nowImpl = fn;
}

export function _ibkrStatusPollerDebugForTests(): {
  subscriberCount: number;
  inflight: boolean;
  misses: number;
  timerOn: boolean;
} {
  return {
    subscriberCount,
    inflight,
    misses,
    timerOn: timer != null,
  };
}
