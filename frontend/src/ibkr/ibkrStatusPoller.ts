/**
 * Single /api/ibkr/status source for the desk.
 *
 * Every useIbkrStatus() subscriber reads this snapshot. One interval, one
 * in-flight fetch. A failed poll marks stale and, after N misses, forces
 * connected=false so the Desk chip / trading gates cannot stay green.
 */
import {
  API_BASE_URL,
  IBKR_STATUS_POLL_MS,
  IBKR_STATUS_STALE_AFTER_MISSES,
} from '../constants';
import { readLastIbkrStatus, writeLastIbkrStatus } from './ibkrStatusCache';
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
  const last = readLastIbkrStatus();
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

function emit(): void {
  listeners.forEach((fn) => fn());
}

function applySuccess(next: IbkrStatus): void {
  misses = 0;
  writeLastIbkrStatus(next);
  snapshot = { ...next, clientReady: true, stale: false, staleSince: null, lastSuccessAt: nowImpl() };
  emit();
}

function applyFailure(): void {
  misses += 1;
  const staleSince = snapshot.staleSince ?? nowImpl();
  const next: IbkrClientStatus = {
    ...snapshot,
    connected: false,
    transport_connected: false,
    clientReady: true,
    stale: true,
    staleSince,
  };
  if (misses >= IBKR_STATUS_STALE_AFTER_MISSES) {
    writeLastIbkrStatus(next);
  }
  snapshot = next;
  emit();
}

export async function pollIbkrStatusOnce(): Promise<void> {
  if (inflight) {
    pending = true;
    return;
  }
  inflight = true;
  try {
    const res = await fetchImpl(`${API_BASE_URL}/api/ibkr/status`);
    if (res.ok) {
      applySuccess((await res.json()) as IbkrStatus);
    } else {
      applyFailure();
    }
  } catch {
    applyFailure();
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

export function getIbkrStatusSnapshot(): IbkrClientStatus {
  return snapshot;
}

export function subscribeIbkrStatus(listener: Listener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    startPolling();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    if (subscriberCount === 0) {
      stopPolling();
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
