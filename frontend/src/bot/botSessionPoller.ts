/**
 * Single owner for bot session / proposals / audit HTTP.
 * Header BotArmControls and StrategyTab share one snapshot. Across
 * Electron+Vite windows, one leader polls; followers apply the share.
 */
import {
  DESK_BOT_POLL_MS,
  DESK_POLL_BOT_SHARE,
  DESK_POLL_LEADER_STALE_MS,
  DESK_POLL_SNAPSHOT_MAX_AGE_MS,
} from '../constants';
import {
  claimDeskPollLeader,
  heartbeatDeskPollLeader,
  publishDeskPollSnap,
  readDeskPollSnap,
  subscribeDeskPollSnap,
} from '../ibkr/deskSharedPoll';
import { fetchBotAudit, fetchBotProposals, fetchBotSession } from './api';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

export interface BotSessionPollSnap {
  session: BotSession | null;
  proposals: BotProposal[];
  audit: BotAuditEntry[];
  error: string | null;
}

const EMPTY: BotSessionPollSnap = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
};

type Listener = () => void;

let snapshot: BotSessionPollSnap = { ...EMPTY };
const listeners = new Set<Listener>();
let subscriberCount = 0;
let intervalVoters = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inflight = false;
let shareUnsub: (() => void) | null = null;

function emit(): void {
  listeners.forEach((fn) => fn());
}

function applySnap(next: BotSessionPollSnap): void {
  snapshot = next;
  emit();
}

function publishLocal(next: BotSessionPollSnap): void {
  applySnap(next);
  publishDeskPollSnap(DESK_POLL_BOT_SHARE, next);
}

function isLeader(): boolean {
  return claimDeskPollLeader(DESK_POLL_BOT_SHARE, DESK_POLL_LEADER_STALE_MS);
}

export async function pollBotSessionOnce(): Promise<void> {
  if (inflight) return;
  if (!isLeader()) {
    const env = readDeskPollSnap<BotSessionPollSnap>(DESK_POLL_BOT_SHARE);
    if (env && Date.now() - env.ts < DESK_POLL_SNAPSHOT_MAX_AGE_MS) {
      applySnap(env.payload);
    }
    return;
  }
  heartbeatDeskPollLeader(DESK_POLL_BOT_SHARE);
  inflight = true;
  try {
    const [session, proposals, audit] = await Promise.all([
      fetchBotSession(),
      fetchBotProposals(),
      fetchBotAudit(),
    ]);
    publishLocal({ session, proposals, audit, error: null });
  } catch (err) {
    applySnap({
      ...snapshot,
      error: err instanceof Error ? err.message : 'bot session failed',
    });
  } finally {
    inflight = false;
  }
}

function stopTimer(): void {
  if (timer != null) {
    clearInterval(timer);
    timer = null;
  }
}

function startTimer(): void {
  if (timer != null || intervalVoters <= 0) return;
  timer = setInterval(() => {
    void pollBotSessionOnce();
  }, DESK_BOT_POLL_MS);
}

function syncShare(): void {
  if (shareUnsub) return;
  shareUnsub = subscribeDeskPollSnap<BotSessionPollSnap>(DESK_POLL_BOT_SHARE, (env) => {
    if (Date.now() - env.ts > DESK_POLL_SNAPSHOT_MAX_AGE_MS) return;
    applySnap(env.payload);
  });
}

export function subscribeBotSession(listener: Listener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    syncShare();
    void pollBotSessionOnce();
    startTimer();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    if (subscriberCount === 0) stopTimer();
  };
}

export function voteBotPollInterval(pollMs: number): () => void {
  if (pollMs <= 0) return () => {};
  intervalVoters += 1;
  startTimer();
  return () => {
    intervalVoters = Math.max(0, intervalVoters - 1);
    if (intervalVoters === 0) stopTimer();
  };
}

export function getBotSessionSnapshot(): BotSessionPollSnap {
  return snapshot;
}

export function applyBotSessionLocal(session: BotSession): void {
  publishLocal({ ...snapshot, session, error: null });
}

export function setBotSessionError(message: string): void {
  applySnap({ ...snapshot, error: message });
}

export function refreshBotSessionNow(): void {
  void pollBotSessionOnce();
}

export function _resetBotSessionPollerForTests(): void {
  stopTimer();
  listeners.clear();
  subscriberCount = 0;
  intervalVoters = 0;
  inflight = false;
  shareUnsub?.();
  shareUnsub = null;
  snapshot = { ...EMPTY };
}

export function _botSessionPollerDebugForTests(): {
  subscriberCount: number;
  intervalVoters: number;
  timerOn: boolean;
} {
  return {
    subscriberCount,
    intervalVoters,
    timerOn: timer != null,
  };
}
