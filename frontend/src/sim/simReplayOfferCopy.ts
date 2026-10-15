/**
 * What a Sim tab's offer says: one sentence and at most one action per state (`offerCopy`), and the
 * window and day labels it names them by. The offer itself is `simReplayOffer.ts`.
 */
import { etTime } from './historicalReplayFormat';
import type { HistoricalWindow, MassiveCap } from './historicalTypes';
import { SIM_ET_TIME_ZONE } from './simConstants';
import { isWholeDay, type ReplayOffer } from './simReplayOffer';

/** "Fri 03:37 ET" -- when a file landed, on the exchange's clock. */
export function landedLabel(epochSeconds: number): string {
  const at = new Date(epochSeconds * 1000);
  const day = at.toLocaleDateString('en-US', { timeZone: SIM_ET_TIME_ZONE, weekday: 'short' });
  const time = at.toLocaleTimeString('en-US', { timeZone: SIM_ET_TIME_ZONE, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  return `${day} ${time} ET`;
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

/** "IMCC · Fri, Sep 18": what an import from the Massive files reads -- the stock-day, not a window. */
export const offerDayLabel = (w: HistoricalWindow) => `${w.symbol} · ${offerDateLabel(w.date)}`;

/** A running import named as it reads: the stock-day, or (an import made before stock-days) its window. */
const importLabel = (w: HistoricalWindow) => (isWholeDay(w) ? offerDayLabel(w) : offerWindowLabel(w));

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
  /** A capped stock-day: what its import holds (`kept`), the window around the playhead, and why. */
  importCapped: (day: string, kept: string, around: string, cap: string) => string;
  readyCapped: (label: string, instead: boolean, cap: string) => string;
  /** A stock-day cut under a smaller cap than today's: the read (or the load) takes the whole day again. */
  importCappedAgain: (day: string, kept: string, limit: string) => string;
  readyCappedAgain: (label: string, instead: boolean, limit: string) => string;
  capWords: (cap: MassiveCap) => string;
  limitWords: (cap: MassiveCap) => string;
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
    // The files are read once per stock-day (ADR 046, 2026-10-09): the day is named, not the playhead's window.
    const day = offerDayLabel(offer.window);
    switch (offer.kind) {
      case 'download':
        if (offer.held && offer.capped) {
          const hours = (w: HistoricalWindow) => `${w.start}–${w.end}`;
          if (offer.capRaised) {
            return { text: t.importCappedAgain(day, hours(offer.held), t.limitWords(offer.capped)), action: 'import' };
          }
          return { text: t.importCapped(day, hours(offer.held), hours(offer.window), t.capWords(offer.capped)), action: 'import' };
        }
        return { text: t.importOffer(day, instead, files.quotes), action: 'import' };
      case 'downloading': {
        const eta = offer.etaSeconds == null ? '' : `, about ${t.duration(offer.etaSeconds)} left`;
        return { text: t.importing(day, `${pct(offer.percent)}${eta}`), action: 'stop' };
      }
      case 'stopped': return { text: t.importStopped(day, offer.percent ? ` at ${offer.percent.toFixed(0)}%` : ''), action: 'import' };
      case 'failed': return { text: t.importFailed(day, offer.error), action: 'import' };
      case 'busy': return { text: t.importBusy(importLabel(offer.running)), action: 'stop-other' };
      default: break;
    }
  }
  switch (offer.kind) {
    case 'download': return { text: t.download(label, instead), action: 'download' };
    case 'ready': {
      const held = offer.held ? offerWindowLabel(offer.held) : label;
      if (!offer.capped) return { text: t.ready(held, instead), action: 'load' };
      return offer.capRaised
        ? { text: t.readyCappedAgain(held, instead, t.limitWords(offer.capped)), action: 'load' }
        : { text: t.readyCapped(held, instead, t.capWords(offer.capped)), action: 'load' };
    }
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
