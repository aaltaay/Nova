/**
 * The one action a Sim tab without its replay should offer: go and get it.
 *
 * Derived entirely from server state -- the jobs list and the clock -- so the
 * offer survives a remount, reads the same from any tab, and agrees with the
 * Historical replay panel: same window defaults, same job row, same progress.
 */
import { progressPercent, validateHistoricalWindow } from './historicalProgress';
import { etTime } from './historicalReplayFormat';
import {
  SIM_HISTORY_GATEWAY_NOT_ANSWERING,
  SIM_HISTORY_GATEWAY_UNREACHABLE,
  SIM_HISTORY_RETRY_INTERVAL_SEC,
  SIM_TAB_NOT_ANSWERING_RETRY_SEC,
  SIM_TAB_WINDOW_END,
  SIM_TAB_WINDOW_START,
} from './simConstants';
import type { IbkrStatus } from '../ibkr/types';
import { isMassive, type HistoricalJob, type HistoricalStatus, type HistoricalWindow } from './historicalTypes';
import type { SimClockState } from './simClockTypes';

/**
 * The day is in the operator's Massive files (ADR 046): the window is read from
 * disk, so no Gateway is needed. `quotes`: the day's bid/ask file is there too.
 */
export interface FromFiles { quotes: boolean }

export type ReplayOffer =
  /** Nothing downloaded for this window yet. */
  | { kind: 'download'; window: HistoricalWindow; fromFiles?: FromFiles }
  /** This window's trades are downloading (or importing from the Massive files) now. */
  | { kind: 'downloading'; window: HistoricalWindow; percent: number | null;
      etaSeconds: number | null; jobId: string;
      /** Prints already committed: loadable now, the rest folds in as it lands. */
      hasCoverage: boolean; fromFiles?: FromFiles }
  /** Started earlier and stopped (paused, interrupted, stalled, queued) -- resumable. */
  | { kind: 'stopped'; window: HistoricalWindow; percent: number | null; fromFiles?: FromFiles }
  /**
   * `gatewayUnreachable`: it failed only because no Gateway port answered, so it
   * heals by itself once one does. `retryAt` (epoch s) honours the backend's
   * retry throttle. `healing` is set by the hook while that retry is under way.
   */
  | { kind: 'failed'; window: HistoricalWindow; error: string; fromFiles?: FromFiles;
      gatewayUnreachable: boolean; retryAt: number | null; healing?: boolean;
      /** When the job last failed (epoch s) -- a failure is the past attempt's, not the Gateway's state now. */
      failedAt?: number | null;
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
  | { kind: 'busy'; window: HistoricalWindow; runningJobId: string; running: HistoricalWindow; fromFiles?: FromFiles };

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
const toMinutes = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5));
const toHhmm = (minutes: number) => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

/**
 * The default window, moved to hold the playhead when it sits outside it: a
 * past day's board clicked at 07:42 (ADR 023) must offer a download that
 * covers 07:42, not the 09:15 open. Same length as the default, starting a
 * quarter hour before the playhead, inside 04:00-20:00.
 */
export function windowAroundPlayhead(clock: SimClockState | null | undefined): { start: string; end: string } {
  const time = clock?.sim_time_et?.slice(11, 16);
  const start = toMinutes(SIM_TAB_WINDOW_START);
  const end = toMinutes(SIM_TAB_WINDOW_END);
  if (!time || !/^\d{2}:\d{2}$/.test(time) || clock?.live_edge) {
    return { start: SIM_TAB_WINDOW_START, end: SIM_TAB_WINDOW_END };
  }
  const at = toMinutes(time);
  if (at >= start && at < end) return { start: SIM_TAB_WINDOW_START, end: SIM_TAB_WINDOW_END };
  const length = end - start;
  const from = Math.min(Math.max(4 * 60, Math.floor(at / 15) * 15 - 15), 20 * 60 - length);
  return { start: toHhmm(from), end: toHhmm(from + length) };
}

export function offerWindow(
  symbol: string,
  clock: SimClockState | null | undefined,
  status: HistoricalStatus | null | undefined,
  now: Date = new Date(),
): HistoricalWindow | null {
  const tab = symbol.trim().toUpperCase();
  for (const date of [clock?.session_date, status?.default_date]) {
    if (!date) continue;
    const bounds = date === clock?.session_date
      ? windowAroundPlayhead(clock)
      : { start: SIM_TAB_WINDOW_START, end: SIM_TAB_WINDOW_END };
    const window = { symbol: tab, date, ...bounds };
    if (validateHistoricalWindow(window, now) == null) return window;
  }
  return null;
}

/**
 * The job a window's Load or Download would act on, by the backend's `auto` rule
 * (ADR 046): its Massive import when there is one; else its IBKR download -- but
 * a day in the Massive files offers an import over an IBKR download that never
 * finished, since Download / Retry there would import from the files anyway.
 */
export function windowJob(window: HistoricalWindow, jobs: readonly HistoricalJob[], fromFiles: FromFiles | null): HistoricalJob | undefined {
  const key = windowKey(window);
  const matches = jobs.filter(row => row.kind === 'trades' && windowKey(row) === key);
  const imported = matches.find(isMassive);
  if (imported) return imported;
  const downloaded = matches.find(row => !isMassive(row));
  return downloaded && (downloaded.status === 'complete' || !fromFiles) ? downloaded : undefined;
}

export function replayOffer(
  window: HistoricalWindow,
  jobs: HistoricalJob[],
  reachable = true,
  /** The day's Massive files when they hold its trades; null otherwise (or not known yet). */
  fromFiles: FromFiles | null = null,
): ReplayOffer {
  const job = windowJob(window, jobs, fromFiles);
  const files = fromFiles ?? undefined;
  // Loading never conflicts with a running download, so "ready" wins outright.
  if (job?.status === 'complete') return { kind: 'ready', window };
  if (job && isProgressing(job)) {
    return {
      kind: 'downloading', window, percent: progressPercent(job),
      // A Massive import is whole or absent: nothing plays before it finishes.
      etaSeconds: job.eta_seconds ?? null, jobId: job.id, hasCoverage: !isMassive(job) && (job.count ?? 0) > 0,
      fromFiles: isMassive(job) ? files ?? { quotes: false } : undefined,
    };
  }
  // One import and one IBKR download may run side by side: only the slot this window would use is busy.
  const importing = Boolean(fromFiles) || isMassive(job);
  const other = jobs.find(row => row !== job && isProgressing(row) && isMassive(row) === importing);
  if (other) {
    return {
      kind: 'busy', window, runningJobId: other.id,
      running: { symbol: other.symbol, date: other.date, start: other.start, end: other.end },
      fromFiles: importing ? files ?? { quotes: false } : undefined,
    };
  }
  if (importing) {
    // Read from disk: Gateway has nothing to do with it.
    if (job?.status === 'failed') {
      return { kind: 'failed', window, error: job.error || 'Import failed', gatewayUnreachable: false, retryAt: null,
        failedAt: job.updated ?? null, fromFiles: files ?? { quotes: false } };
    }
    if (job) return { kind: 'stopped', window, percent: progressPercent(job), fromFiles: files ?? { quotes: false } };
    return { kind: 'download', window, fromFiles: files };
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
      failedAt: job.updated ?? null,
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

/** `import`: read the window from the Massive files -- the same request as `download`, which picks the files. */
export type OfferAction = 'download' | 'import' | 'load' | 'resume' | 'retry' | 'start-gateway' | 'stop' | 'stop-other' | 'reconnect';

export interface OfferCopy { text: string; action: OfferAction | null }

type CopyText = {
  /** A day in the Massive files (ADR 046). */
  importOffer: (label: string, instead: boolean, quotes: boolean) => string;
  importing: (label: string, progress: string) => string;
  importStopped: (label: string, progress: string) => string;
  importFailed: (label: string, error: string) => string;
  importBusy: (runningLabel: string) => string;
  download: (label: string, instead: boolean) => string;
  ready: (label: string, instead: boolean) => string;
  downloading: (label: string, progress: string, hasCoverage: boolean) => string;
  stopped: (label: string, progress: string) => string;
  failed: (label: string, error: string) => string;
  busy: (runningLabel: string) => string;
  gatewayDown: (label: string) => string;
  gatewayWaiting: (label: string) => string;
  retrying: (label: string) => string;
  notAnswering: (label: string, attempt: number, max: number, failedAt?: string | null) => string;
  notAnsweringGaveUp: (label: string, failedAt?: string | null) => string;
  duration: (seconds: number) => string;
};

/** One sentence and at most one action per state. `instead` = another symbol is loaded. */
export function offerCopy(offer: ReplayOffer, instead: boolean, t: CopyText): OfferCopy {
  const label = offerWindowLabel(offer.window);
  const pct = (percent: number | null) => (percent == null ? '' : ` -- ${percent.toFixed(0)}%`);
  if ('fromFiles' in offer && offer.fromFiles) {
    const files = offer.fromFiles;
    switch (offer.kind) {
      case 'download': return { text: t.importOffer(label, instead, files.quotes), action: 'import' };
      case 'downloading': {
        const eta = offer.etaSeconds == null ? '' : `, about ${t.duration(offer.etaSeconds)} left`;
        return { text: t.importing(label, `${pct(offer.percent)}${eta}`), action: 'stop' };
      }
      case 'stopped': return { text: t.importStopped(label, offer.percent ? ` at ${offer.percent.toFixed(0)}%` : ''), action: 'import' };
      case 'failed': return { text: t.importFailed(label, offer.error), action: 'import' };
      case 'busy': return { text: t.importBusy(offerWindowLabel(offer.running)), action: 'stop-other' };
      default: break;
    }
  }
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
        const failedAt = offer.failedAt != null && Number.isFinite(offer.failedAt) ? etTime(offer.failedAt).slice(0, 5) : null;
        return offer.gaveUp || !offer.healing
          ? { text: t.notAnsweringGaveUp(label, failedAt), action: 'reconnect' }
          : { text: t.notAnswering(label, offer.attempt ?? 1, offer.maxAttempts ?? 1, failedAt), action: 'reconnect' };
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
