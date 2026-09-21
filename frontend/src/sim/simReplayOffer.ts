/**
 * The one action a Sim tab without its replay should offer: go and get it.
 *
 * Derived entirely from server state -- the jobs list and the clock -- so the
 * offer survives a remount, reads the same from any tab, and agrees with the
 * Historical replay panel: same window defaults, same job row, same progress.
 */
import { progressPercent, validateHistoricalWindow } from './historicalProgress';
import {
  SIM_HISTORY_GATEWAY_UNREACHABLE,
  SIM_HISTORY_RETRY_INTERVAL_SEC,
  SIM_TAB_WINDOW_END,
  SIM_TAB_WINDOW_START,
} from './simConstants';
import type { IbkrStatus } from '../ibkr/types';
import type { HistoricalJob, HistoricalStatus, HistoricalWindow } from './historicalTypes';
import type { SimClockState } from './simClockTypes';

export type ReplayOffer =
  /** Nothing downloaded for this window yet. */
  | { kind: 'download'; window: HistoricalWindow }
  /** This window's trades are downloading now. */
  | { kind: 'downloading'; window: HistoricalWindow; percent: number | null;
      etaSeconds: number | null; jobId: string }
  /** Started earlier and stopped (paused, interrupted, stalled, queued) -- resumable. */
  | { kind: 'stopped'; window: HistoricalWindow; percent: number | null }
  /**
   * `gatewayUnreachable`: it failed only because no Gateway port answered, so it
   * heals by itself once one does. `retryAt` (epoch s) honours the backend's
   * retry throttle. `healing` is set by the hook while that retry is under way.
   */
  | { kind: 'failed'; window: HistoricalWindow; error: string;
      gatewayUnreachable: boolean; retryAt: number | null; healing?: boolean }
  /** No Gateway port answers; `waiting` once the operator asked to start it. */
  | { kind: 'gateway-down'; window: HistoricalWindow; waiting?: boolean }
  /** Downloaded and waiting to be loaded. */
  | { kind: 'ready'; window: HistoricalWindow }
  /** Another window is downloading; the backend runs one at a time, so a click would only be refused. */
  | { kind: 'busy'; window: HistoricalWindow; runningSymbol: string };

/** Backend `history_store.ACTIVE` -- the only statuses that are really progressing. */
const ACTIVE = new Set(['running', 'pause_requested']);
const isProgressing = (job: HistoricalJob) => ACTIVE.has(job.status) && !job.stale;

export const windowKey = (w: HistoricalWindow) => `${w.symbol}|${w.date}|${w.start}|${w.end}`;

/**
 * Can a replay download reach IB Gateway right now?
 *
 * Reads the honest fields only. Sim overlays `connected` to keep the desk
 * usable, but `transport_connected` and the two port probes are left alone --
 * and the downloader tries both ports, so either one listening is enough.
 * Unknown (fields absent) counts as reachable: never block a click on a guess.
 */
export function gatewayReachable(status: Partial<IbkrStatus> | null | undefined): boolean {
  if (!status) return true;
  const signals = [status.transport_connected, status.preferred_port_reachable, status.alternate_port_reachable];
  if (signals.every(signal => signal == null)) return true;
  return signals.some(Boolean);
}

/**
 * The date on the desk when it is a finished session, else the panel's default.
 *
 * The backend refuses any window that has not ended, and mid-session the clock's
 * date is today -- so the desk date is preferred only when it would be accepted.
 * Both are real dates the operator can see; neither is invented here.
 */
export function offerWindow(
  symbol: string,
  clock: SimClockState | null | undefined,
  status: HistoricalStatus | null | undefined,
  now: Date = new Date(),
): HistoricalWindow | null {
  const tab = symbol.trim().toUpperCase();
  for (const date of [clock?.session_date, status?.default_date]) {
    if (!date) continue;
    const window = { symbol: tab, date, start: SIM_TAB_WINDOW_START, end: SIM_TAB_WINDOW_END };
    if (validateHistoricalWindow(window, now) == null) return window;
  }
  return null;
}

export function replayOffer(
  window: HistoricalWindow,
  jobs: HistoricalJob[],
  reachable = true,
): ReplayOffer {
  const key = windowKey(window);
  const job = jobs.find(row => row.kind === 'trades' && windowKey(row) === key);
  // Loading never conflicts with a running download, so "ready" wins outright.
  if (job?.status === 'complete') return { kind: 'ready', window };
  if (job && isProgressing(job)) {
    return {
      kind: 'downloading', window, percent: progressPercent(job),
      etaSeconds: job.eta_seconds ?? null, jobId: job.id,
    };
  }
  const other = jobs.find(row => row !== job && isProgressing(row));
  if (other) return { kind: 'busy', window, runningSymbol: other.symbol };
  // Everything below needs Gateway; offering it while both ports are dark would
  // only reproduce the refusal the operator just read.
  if (!reachable) return { kind: 'gateway-down', window };
  if (job?.status === 'failed') {
    const error = job.error || 'Download failed';
    return {
      kind: 'failed', window, error,
      gatewayUnreachable: error.startsWith(SIM_HISTORY_GATEWAY_UNREACHABLE),
      retryAt: job.updated == null ? null : job.updated + SIM_HISTORY_RETRY_INTERVAL_SEC,
    };
  }
  if (job) return { kind: 'stopped', window, percent: progressPercent(job) };
  return { kind: 'download', window };
}

/** "Fri, Sep 18" -- the same shape the Sim session bar prints. */
export function offerDateLabel(iso: string): string {
  const day = new Date(`${iso}T12:00:00Z`);
  if (!Number.isFinite(day.getTime())) return iso;
  return day.toLocaleDateString('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' });
}

/** "IMCC · Fri, Sep 18 · 04:00–20:00 ET": the window is always stated, never implied. */
export const offerWindowLabel = (w: HistoricalWindow) =>
  `${w.symbol} · ${offerDateLabel(w.date)} · ${w.start}–${w.end} ET`;

export type OfferAction = 'download' | 'load' | 'resume' | 'retry' | 'start-gateway' | 'stop';

export interface OfferCopy { text: string; action: OfferAction | null }

type CopyText = {
  download: (label: string, instead: boolean) => string;
  ready: (label: string, instead: boolean) => string;
  downloading: (label: string, progress: string) => string;
  stopped: (label: string, progress: string) => string;
  failed: (label: string, error: string) => string;
  busy: (runningSymbol: string, tab: string) => string;
  gatewayDown: (label: string) => string;
  gatewayWaiting: (label: string) => string;
  retrying: (label: string) => string;
  duration: (seconds: number) => string;
};

/** One sentence and at most one action per state. `instead` = another symbol is loaded. */
export function offerCopy(offer: ReplayOffer, instead: boolean, t: CopyText): OfferCopy {
  const label = offerWindowLabel(offer.window);
  const pct = (percent: number | null) => (percent == null ? '' : ` -- ${percent.toFixed(0)}%`);
  switch (offer.kind) {
    case 'download': return { text: t.download(label, instead), action: 'download' };
    case 'ready': return { text: t.ready(label, instead), action: 'load' };
    case 'downloading': {
      const eta = offer.etaSeconds == null ? '' : `, about ${t.duration(offer.etaSeconds)} left`;
      // Stoppable on purpose: the backend runs one download at a time, so a
       // long job the operator no longer wants blocks every other one.
      return { text: t.downloading(label, `${pct(offer.percent)}${eta}`), action: 'stop' };
    }
    case 'stopped': return { text: t.stopped(label, offer.percent ? ` at ${offer.percent.toFixed(0)}%` : ''), action: 'resume' };
    case 'failed':
      return offer.healing
        ? { text: t.retrying(label), action: null }
        : { text: t.failed(label, offer.error), action: 'retry' };
    case 'busy': return { text: t.busy(offer.runningSymbol, offer.window.symbol), action: null };
    case 'gateway-down':
      return offer.waiting
        ? { text: t.gatewayWaiting(label), action: null }
        : { text: t.gatewayDown(label), action: 'start-gateway' };
  }
}
