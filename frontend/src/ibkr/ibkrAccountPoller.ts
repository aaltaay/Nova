/**
 * Single owner for IBKR account / positions / orders HTTP.
 * One interval per process. Across Electron+Vite windows, one leader polls
 * at IBKR_ACCOUNT_POLL_MS; followers apply a shared snapshot so Day P&L
 * stays 1s-honest without N-window storms.
 */
import {
  API_BASE_URL,
  DESK_POLL_ACCOUNT_SHARE,
  DESK_POLL_LEADER_STALE_MS,
  DESK_POLL_SNAPSHOT_MAX_AGE_MS,
  IBKR_ACCOUNT_POLL_MS,
  IBKR_ORDERS_POLL_MS,
} from '../constants';
import { lastKnownAsOfMessage } from './disconnectCopy';
import {
  claimDeskPollLeader,
  heartbeatDeskPollLeader,
  publishDeskPollSnap,
  readDeskPollSnap,
  subscribeDeskPollSnap,
} from './deskSharedPoll';
import { fetchAccountCluster, fetchOrdersCluster } from './ibkrAccountFetch';
import type { IbkrAccountSummary, IbkrOrder, IbkrPosition } from './types';

export interface IbkrAccountPollSnap {
  summary: IbkrAccountSummary | null;
  positions: IbkrPosition[];
  orders: IbkrOrder[];
  closedOrders: IbkrOrder[];
  loading: boolean;
  error: string | null;
  stale: boolean;
  staleSince: number | null;
}

const EMPTY: IbkrAccountPollSnap = {
  summary: null,
  positions: [],
  orders: [],
  closedOrders: [],
  loading: false,
  error: null,
  stale: false,
  staleSince: null,
};

type Listener = () => void;

let snapshot: IbkrAccountPollSnap = { ...EMPTY };
const listeners = new Set<Listener>();
let subscriberCount = 0;
let connected = false;
let sample = false;
let hadSession = false;
let accountTimer: ReturnType<typeof setInterval> | null = null;
let ordersTimer: ReturnType<typeof setInterval> | null = null;
let accountInflight = false;
let ordersInflight = false;
let accountFails: string[] = [];
let orderFails: string[] = [];
let shareUnsub: (() => void) | null = null;

function emit(): void {
  listeners.forEach((fn) => fn());
}

function mergeError(): string | null {
  const failures = [...accountFails, ...orderFails];
  return failures.length ? `IBKR read failed -- ${failures.join(', ')}` : null;
}

function applySnap(next: IbkrAccountPollSnap): void {
  snapshot = next;
  emit();
}

function publishLocal(next: IbkrAccountPollSnap): void {
  applySnap(next);
  if (connected && !sample) {
    publishDeskPollSnap(DESK_POLL_ACCOUNT_SHARE, next);
  }
}

function applyRemote(remote: IbkrAccountPollSnap): void {
  if (!connected || sample) return;
  applySnap({ ...remote, stale: false });
}

function isLeader(): boolean {
  return claimDeskPollLeader(DESK_POLL_ACCOUNT_SHARE, DESK_POLL_LEADER_STALE_MS);
}

async function tickAccount(): Promise<void> {
  if (sample || !connected || accountInflight) return;
  if (!isLeader()) {
    const env = readDeskPollSnap<IbkrAccountPollSnap>(DESK_POLL_ACCOUNT_SHARE);
    if (env && Date.now() - env.ts < DESK_POLL_SNAPSHOT_MAX_AGE_MS) {
      applyRemote(env.payload);
    }
    return;
  }
  heartbeatDeskPollLeader(DESK_POLL_ACCOUNT_SHARE);
  accountInflight = true;
  applySnap({ ...snapshot, loading: true });
  try {
    const snap = await fetchAccountCluster(API_BASE_URL);
    if (snap.summary) snapshot = { ...snapshot, summary: snap.summary };
    if (snap.positions) snapshot = { ...snapshot, positions: snap.positions };
    accountFails = snap.failures;
    publishLocal({
      ...snapshot,
      loading: false,
      error: mergeError(),
      stale: false,
      staleSince: null,
    });
  } catch (err) {
    console.error('[Nova] IBKR account/positions poll failed', err);
    accountFails = ['account/positions fetch failed -- retrying'];
    applySnap({ ...snapshot, loading: false, error: mergeError() });
  } finally {
    accountInflight = false;
  }
}

async function tickOrders(): Promise<void> {
  if (sample || !connected || ordersInflight) return;
  if (!isLeader()) {
    const env = readDeskPollSnap<IbkrAccountPollSnap>(DESK_POLL_ACCOUNT_SHARE);
    if (env && Date.now() - env.ts < DESK_POLL_SNAPSHOT_MAX_AGE_MS) {
      applyRemote(env.payload);
    }
    return;
  }
  heartbeatDeskPollLeader(DESK_POLL_ACCOUNT_SHARE);
  ordersInflight = true;
  try {
    const snap = await fetchOrdersCluster(API_BASE_URL);
    if (snap.orders) snapshot = { ...snapshot, orders: snap.orders };
    if (snap.closedOrders) snapshot = { ...snapshot, closedOrders: snap.closedOrders };
    orderFails = snap.failures;
    publishLocal({ ...snapshot, error: mergeError() });
  } catch (err) {
    console.error('[Nova] IBKR orders poll failed', err);
    orderFails = ['orders fetch failed -- retrying'];
    applySnap({ ...snapshot, error: mergeError() });
  } finally {
    ordersInflight = false;
  }
}

function stopTimers(): void {
  if (accountTimer != null) {
    clearInterval(accountTimer);
    accountTimer = null;
  }
  if (ordersTimer != null) {
    clearInterval(ordersTimer);
    ordersTimer = null;
  }
}

function startTimers(): void {
  if (accountTimer != null || sample || !connected) return;
  void tickAccount();
  void tickOrders();
  accountTimer = setInterval(() => {
    void tickAccount();
  }, IBKR_ACCOUNT_POLL_MS);
  ordersTimer = setInterval(() => {
    void tickOrders();
  }, IBKR_ORDERS_POLL_MS);
}

function applyDisconnected(): void {
  if (!hadSession) {
    applySnap({ ...snapshot, loading: false });
    return;
  }
  const since = snapshot.staleSince ?? Date.now();
  applySnap({
    ...snapshot,
    loading: false,
    stale: true,
    staleSince: since,
    error: lastKnownAsOfMessage(since),
  });
}

export function configureIbkrAccountPoller(opts: {
  connected: boolean;
  sample: boolean;
}): void {
  const nextConnected = opts.connected;
  const nextSample = opts.sample;
  const changed = nextConnected !== connected || nextSample !== sample;
  connected = nextConnected;
  sample = nextSample;
  if (sample) {
    stopTimers();
    return;
  }
  if (connected) {
    hadSession = true;
    if (subscriberCount > 0) startTimers();
    return;
  }
  stopTimers();
  if (changed) applyDisconnected();
}

function syncShare(): void {
  if (shareUnsub) return;
  shareUnsub = subscribeDeskPollSnap<IbkrAccountPollSnap>(
    DESK_POLL_ACCOUNT_SHARE,
    (env) => {
      if (!connected || sample) return;
      if (Date.now() - env.ts > DESK_POLL_SNAPSHOT_MAX_AGE_MS) return;
      applyRemote(env.payload);
    },
  );
}

export function subscribeIbkrAccount(listener: Listener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    syncShare();
    startTimers();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    if (subscriberCount === 0) stopTimers();
  };
}

export function getIbkrAccountSnapshot(): IbkrAccountPollSnap {
  return snapshot;
}

export function refreshIbkrAccountNow(): void {
  void tickAccount();
  void tickOrders();
}

export function _resetIbkrAccountPollerForTests(): void {
  stopTimers();
  listeners.clear();
  subscriberCount = 0;
  connected = false;
  sample = false;
  hadSession = false;
  accountInflight = false;
  ordersInflight = false;
  accountFails = [];
  orderFails = [];
  shareUnsub?.();
  shareUnsub = null;
  snapshot = { ...EMPTY };
}

export function _ibkrAccountPollerDebugForTests(): {
  subscriberCount: number;
  timerOn: boolean;
  accountInflight: boolean;
} {
  return {
    subscriberCount,
    timerOn: accountTimer != null,
    accountInflight,
  };
}
