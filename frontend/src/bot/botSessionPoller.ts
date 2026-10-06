/**
 * Single owner for bot session / proposals / audit HTTP.
 * The Bots page hero, the Trader rail card and the page's cards share one snapshot. Across
 * Electron+Vite windows, one leader polls; followers apply the share.
 */
import {
  DESK_BOT_POLL_MS,
  DESK_POLL_BOT_SHARE,
  DESK_POLL_LEADER_STALE_MS,
  DESK_POLL_SNAPSHOT_MAX_AGE_MS,
} from '../constants';
import { BOT_LABEL_SESSION } from '../constantGroups/bot';
import {
  claimDeskPollLeader,
  heartbeatDeskPollLeader,
  publishDeskPollSnap,
  readDeskPollSnap,
  subscribeDeskPollSnap,
  getConfirmedDeskVenueSnapshot,
  isConfirmedDeskVenueSnapshotCurrent,
  subscribeConfirmedDeskVenue,
  watchDeskRequestRoute,
  type ConfirmedDeskVenueSnapshot,
} from '../ibkr';
import { SAMPLE_BOT_ABSENT } from '../sample_data/sampleCopy';
import { isSampleView } from '../sample_data/sampleNav';
import { fetchBotAudit, fetchBotProposals, fetchBotSession } from './api';
import { botUnreadableMessage, parseBotAudit, parseBotProposals, parseBotSession } from './botPayload';
import type { BotAuditEntry, BotProposal, BotSession } from './types';

export interface BotSessionPollSnap {
  session: BotSession | null;
  proposals: BotProposal[];
  audit: BotAuditEntry[];
  error: string | null;
  errorSticky: boolean;
}

/** Shared schema 1 refuses the old unscoped cache after any venue transition. */
interface BotSessionPollShare {
  schema_version: 1;
  scope: ConfirmedDeskVenueSnapshot;
  snap: BotSessionPollSnap;
}

const EMPTY: BotSessionPollSnap = {
  session: null,
  proposals: [],
  audit: [],
  error: null,
  errorSticky: false,
};

/** V4: the sample desk has no bot -- a stated absence, never the live bot's session. */
const SAMPLE_SNAP: BotSessionPollSnap = { ...EMPTY, error: SAMPLE_BOT_ABSENT, errorSticky: true };

/** A snapshot shared by another window is re-checked before this one renders it (C12). */
function normalizeSnap(raw: BotSessionPollSnap): BotSessionPollSnap {
  return {
    session: raw?.session == null ? null : parseBotSession(raw.session),
    proposals: parseBotProposals({ proposals: raw?.proposals }) ?? [],
    audit: parseBotAudit({ entries: raw?.audit }) ?? [],
    error: typeof raw?.error === 'string' ? raw.error : null,
    errorSticky: raw?.errorSticky === true,
  };
}

type Listener = () => void;

let snapshot: BotSessionPollSnap = { ...EMPTY };
const listeners = new Set<Listener>();
let subscriberCount = 0;
let intervalVoters = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inflight = false;
let pending = false;
let applyEpoch = 0;
let shareUnsub: (() => void) | null = null;
let venueUnsub: (() => void) | null = null;
let snapshotScope = getConfirmedDeskVenueSnapshot();

function bumpApplyEpoch(): number {
  applyEpoch += 1;
  return applyEpoch;
}

function emit(): void {
  listeners.forEach((fn) => fn());
}

function applySnap(next: BotSessionPollSnap): void {
  snapshot = next;
  emit();
}

function publishLocal(next: BotSessionPollSnap, scope: ConfirmedDeskVenueSnapshot): void {
  snapshotScope = scope;
  applySnap(next);
  publishDeskPollSnap<BotSessionPollShare>(DESK_POLL_BOT_SHARE, { schema_version: 1, scope, snap: next });
}

function matchesSession(session: BotSession | null, scope: ConfirmedDeskVenueSnapshot): boolean {
  return scope.venue !== null && scope.generation !== null
    && session?.level_venue === scope.venue;
}

function applyShare(raw: BotSessionPollShare): void {
  if (raw?.schema_version !== 1 || !raw.scope || !isConfirmedDeskVenueSnapshotCurrent(raw.scope)) return;
  const next = normalizeSnap(raw.snap);
  if (!matchesSession(next.session, raw.scope)) return;
  snapshotScope = raw.scope;
  applySnap(next);
}

function onConfirmedVenueChange(refresh = true): void {
  const scope = getConfirmedDeskVenueSnapshot();
  if (scope.venue === snapshotScope.venue && scope.generation === snapshotScope.generation) return;
  snapshotScope = scope;
  bumpApplyEpoch();
  applySnap({ ...EMPTY });
  if (refresh) void pollBotSessionOnce();
}

function isLeader(): boolean {
  return claimDeskPollLeader(DESK_POLL_BOT_SHARE, DESK_POLL_LEADER_STALE_MS);
}

export async function pollBotSessionOnce(): Promise<void> {
  if (isSampleView()) return;
  if (inflight) { pending = true; return; }
  const scope = getConfirmedDeskVenueSnapshot();
  if (!isLeader()) {
    const env = readDeskPollSnap<BotSessionPollShare>(DESK_POLL_BOT_SHARE);
    if (env && Date.now() - env.ts < DESK_POLL_SNAPSHOT_MAX_AGE_MS) {
      applyShare(env.payload);
    }
    return;
  }
  heartbeatDeskPollLeader(DESK_POLL_BOT_SHARE);
  inflight = true;
  const epoch = applyEpoch;
  const route = watchDeskRequestRoute();
  try {
    const [session, proposals, audit] = await Promise.all([
      fetchBotSession(),
      fetchBotProposals(),
      fetchBotAudit(),
    ]);
    if (!route.isCurrent() || epoch !== applyEpoch || !isConfirmedDeskVenueSnapshotCurrent(scope)) return;
    if (!matchesSession(session, scope)) return;
    publishLocal({
      session,
      proposals,
      audit,
      error: snapshot.errorSticky ? snapshot.error : null,
      errorSticky: snapshot.errorSticky,
    }, scope);
  } catch (err) {
    if (!route.isCurrent() || epoch !== applyEpoch || !isConfirmedDeskVenueSnapshotCurrent(scope)) return;
    applySnap({
      ...snapshot,
      error: snapshot.errorSticky
        ? snapshot.error
        : err instanceof Error ? err.message : 'bot session failed',
    });
  } finally {
    route.dispose();
    inflight = false;
    if (pending) {
      pending = false;
      void pollBotSessionOnce();
    }
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
  shareUnsub = subscribeDeskPollSnap<BotSessionPollShare>(DESK_POLL_BOT_SHARE, (env) => {
    if (Date.now() - env.ts > DESK_POLL_SNAPSHOT_MAX_AGE_MS) return;
    applyShare(env.payload);
  });
}

export function subscribeBotSession(listener: Listener): () => void {
  listeners.add(listener);
  subscriberCount += 1;
  if (subscriberCount === 1) {
    onConfirmedVenueChange(false);
    venueUnsub = subscribeConfirmedDeskVenue(() => onConfirmedVenueChange());
    syncShare();
    void pollBotSessionOnce();
    startTimer();
  }
  return () => {
    listeners.delete(listener);
    subscriberCount = Math.max(0, subscriberCount - 1);
    if (subscriberCount === 0) {
      stopTimer();
      venueUnsub?.();
      venueUnsub = null;
      shareUnsub?.();
      shareUnsub = null;
    }
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
  if (isSampleView()) return SAMPLE_SNAP;
  return isConfirmedDeskVenueSnapshotCurrent(snapshotScope) ? snapshot : EMPTY;
}

export function applyBotSessionLocal(session: BotSession): void {
  const scope = getConfirmedDeskVenueSnapshot();
  if (!matchesSession(session, scope) || !isConfirmedDeskVenueSnapshotCurrent(scope)) return;
  bumpApplyEpoch();
  publishLocal({ ...snapshot, session, error: null, errorSticky: false }, scope);
}

export function setBotSessionError(message: string): void {
  applySnap({ ...snapshot, error: message, errorSticky: true });
}

export async function runBotSessionWrite(
  work: () => Promise<BotSession>,
): Promise<BotSession | null> {
  const scope = getConfirmedDeskVenueSnapshot();
  const epoch = bumpApplyEpoch();
  const route = watchDeskRequestRoute();
  // A write answer the page cannot render is refused, never applied (C12).
  let answer: BotSession;
  try { answer = await work(); }
  catch (error) {
    if (!route.isCurrent() || epoch !== applyEpoch || !isConfirmedDeskVenueSnapshotCurrent(scope)) return null;
    throw error;
  }
  finally { route.dispose(); }
  if (!route.isCurrent() || epoch !== applyEpoch || !isConfirmedDeskVenueSnapshotCurrent(scope)) return null;
  const next = parseBotSession(answer);
  if (!next) throw new Error(botUnreadableMessage(BOT_LABEL_SESSION, 0));
  if (!matchesSession(next, scope)) return null;
  applyBotSessionLocal(next);
  return next;
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
  pending = false;
  applyEpoch = 0;
  shareUnsub?.();
  shareUnsub = null;
  venueUnsub?.();
  venueUnsub = null;
  snapshotScope = getConfirmedDeskVenueSnapshot();
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
