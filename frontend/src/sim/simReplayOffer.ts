/**
 * The one action a Sim tab without its replay should offer: go and get it.
 *
 * Derived entirely from server state -- the jobs list and the clock -- so the
 * offer survives a remount, reads the same from any tab, and agrees with the
 * Historical replay panel: same window defaults, same job row, same progress.
 */
import { progressPercent, validateHistoricalWindow } from './historicalProgress';
import {
  SIM_HISTORY_GATEWAY_NOT_ANSWERING,
  SIM_HISTORY_GATEWAY_UNREACHABLE,
  SIM_HISTORY_RETRY_INTERVAL_SEC,
  SIM_TAB_NOT_ANSWERING_RETRY_SEC,
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
      etaSeconds: number | null; jobId: string;
      /** Prints already committed: loadable now, the rest folds in as it lands. */
      hasCoverage: boolean }
  /** Started earlier and stopped (paused, interrupted, stalled, queued) -- resumable. */
  | { kind: 'stopped'; window: HistoricalWindow; percent: number | null }
  /**
   * `gatewayUnreachable`: it failed only because no Gateway port answered, so it
   * heals by itself once one does. `retryAt` (epoch s) honours the backend's
   * retry throttle. `healing` is set by the hook while that retry is under way.
   */
  | { kind: 'failed'; window: HistoricalWindow; error: string;
      gatewayUnreachable: boolean; retryAt: number | null; healing?: boolean;
      /** Gateway took the connection but IBKR never answered: retried slowly, reconnect offered. */
      gatewayNotAnswering?: boolean;
      /** Set by the hook while a not-answering failure is being retried / after it gave up. */
      attempt?: number; maxAttempts?: number; gaveUp?: boolean }
  /** No Gateway port answers; `waiting` once the operator asked to start it. */
  | { kind: 'gateway-down'; window: HistoricalWindow; waiting?: boolean }
  /** Downloaded and waiting to be loaded. */
  | { kind: 'ready'; window: HistoricalWindow }
  /**
   * Another window holds the one download slot the backend allows. A plain
   * Download would only be refused, so the offer is to stop that one and start
   * this -- `running` names it, because "an IMCC download" is ambiguous when it
   * is a different IMCC window.
   */
  | { kind: 'busy'; window: HistoricalWindow; runningJobId: string; running: HistoricalWindow };

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
      etaSeconds: job.eta_seconds ?? null, jobId: job.id, hasCoverage: (job.count ?? 0) > 0,
    };
  }
  const other = jobs.find(row => row !== job && isProgressing(row));
  if (other) {
    return {
      kind: 'busy', window, runningJobId: other.id,
      running: { symbol: other.symbol, date: other.date, start: other.start, end: other.end },
    };
  }
  // Everything below needs Gateway; offering it while both ports are dark would
  // only reproduce the refusal the operator just read.
  if (!reachable) return { kind: 'gateway-down', window };
  if (job?.status === 'failed') {
    const error = job.error || 'Download failed';
    const gatewayNotAnswering = error.startsWith(SIM_HISTORY_GATEWAY_NOT_ANSWERING);
    const wait = gatewayNotAnswering ? SIM_TAB_NOT_ANSWERING_RETRY_SEC : SIM_HISTORY_RETRY_INTERVAL_SEC;
    return {
      kind: 'failed', window, error,
      gatewayUnreachable: error.startsWith(SIM_HISTORY_GATEWAY_UNREACHABLE),
      gatewayNotAnswering,
      retryAt: job.updated == null ? null : job.updated + wait,
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

export type OfferAction = 'download' | 'load' | 'resume' | 'retry' | 'start-gateway' | 'stop' | 'stop-other' | 'reconnect';

export interface OfferCopy { text: string; action: OfferAction | null }

type CopyText = {
  download: (label: string, instead: boolean) => string;
  ready: (label: string, instead: boolean) => string;
  downloading: (label: string, progress: string, hasCoverage: boolean) => string;
  stopped: (label: string, progress: string) => string;
  failed: (label: string, error: string) => string;
  busy: (runningLabel: string) => string;
  gatewayDown: (label: string) => string;
  gatewayWaiting: (label: string) => string;
  retrying: (label: string) => string;
  notAnswering: (label: string, attempt: number, max: number) => string;
  notAnsweringGaveUp: (label: string) => string;
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
      const progress = `${pct(offer.percent)}${eta}`;
      // With prints committed the replay is loadable now (the rest folds in via
      // useProgressiveReplay). Before the first page, Stop: the backend runs one
      // download at a time, so a job the operator no longer wants blocks all.
      return offer.hasCoverage
        ? { text: t.downloading(label, progress, true), action: 'load' }
        : { text: t.downloading(label, progress, false), action: 'stop' };
    }
    case 'stopped': return { text: t.stopped(label, offer.percent ? ` at ${offer.percent.toFixed(0)}%` : ''), action: 'resume' };
    case 'failed':
      if (offer.gatewayNotAnswering) {
        return offer.gaveUp || !offer.healing
          ? { text: t.notAnsweringGaveUp(label), action: 'reconnect' }
          : { text: t.notAnswering(label, offer.attempt ?? 1, offer.maxAttempts ?? 1), action: 'reconnect' };
      }
      return offer.healing
        ? { text: t.retrying(label), action: null }
        : { text: t.failed(label, offer.error), action: 'retry' };
    case 'busy': return { text: t.busy(offerWindowLabel(offer.running)), action: 'stop-other' };
    case 'gateway-down':
      return offer.waiting
        ? { text: t.gatewayWaiting(label), action: null }
        : { text: t.gatewayDown(label), action: 'start-gateway' };
  }
}
