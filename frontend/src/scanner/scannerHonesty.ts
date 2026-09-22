/** Scanner roster / L1 honesty -- last-good, feed_error, no L1 yet. */

import type { ScannerTableMeta } from '../hooks/useScannerPriceStream';
import { frozenTableLabel } from '../hooks/useScannerPriceStream';
import type { ScannerRow } from '../types/scanner';
import { carryQuoteQuality, normalizeScannerRows } from './scannerRowShape';

export const SCANNER_PRICE_NO_L1 = 'no L1 yet';
export const SCANNER_HONESTY_UNAVAILABLE = 'unavailable';
export const SCANNER_HONESTY_LAST_GOOD = 'last-good';
export const SCANNER_HONESTY_CHIP_ROLE = 'Roster';
export const SCANNER_HONESTY_LAST_GOOD_LABEL = 'Last-good -- empty update ignored';
export const SCANNER_CATALYSTS_EMPTY = 'No news catalysts on the IBKR roster right now.';
export const SCANNER_CATALYSTS_FEED_DOWN = 'Catalysts feed is down.';
export const SCANNER_CATALYSTS_FETCH_FAILED = 'Catalysts feed failed -- request did not complete.';
export const SCANNER_CATALYSTS_UNREADABLE = 'Catalysts feed failed -- the reply was not readable.';

export type HonestySignals = {
  feedError?: string | null;
  subscriptionError?: string | null;
  tableState?: string | null;
  lastGood?: boolean;
};

/** Keep previous rows when an empty payload arrives (last-good since 2026-07-20). */
export function applyLastGoodRows<T>(
  prev: T[],
  incoming: unknown,
): { rows: T[]; lastGood: boolean } | null {
  if (!Array.isArray(incoming)) return null;
  if (incoming.length === 0 && prev.length > 0) {
    return { rows: prev, lastGood: true };
  }
  return { rows: incoming as T[], lastGood: false };
}

/**
 * Replace one table's rows from a REST / roster payload. Every row passes the
 * shape gate first (scannerRowShape: a row without a symbol is dropped, a
 * non-finite number is null), so a malformed row can never reach a renderer.
 */
export function applyRosterTable<T extends ScannerRow>(
  setter: (fn: (prev: T[]) => T[]) => void,
  setLastGood: (fn: (prev: Record<string, boolean>) => Record<string, boolean>) => void,
  table: string,
  incoming: unknown,
): void {
  const rows = normalizeScannerRows(incoming) as T[] | null;
  if (!rows) return;
  setter(prev => {
    const next = applyLastGoodRows(prev, rows);
    if (!next) return prev;
    setLastGood(map => (map[table] === next.lastGood ? map : { ...map, [table]: next.lastGood }));
    return next.lastGood ? next.rows : carryQuoteQuality(prev, next.rows);
  });
}

export function mergeRestTableMeta(
  prev: Record<string, ScannerTableMeta>,
  table: string,
  state: unknown,
  rosterTs: unknown,
): Record<string, ScannerTableMeta> {
  if (typeof state !== 'string' || !state) return prev;
  const prevMeta = prev[table];
  return {
    ...prev,
    [table]: {
      state,
      session_key: prevMeta?.session_key ?? '',
      revision: prevMeta?.revision ?? 0,
      roster_ts: typeof rosterTs === 'number' ? rosterTs : prevMeta?.roster_ts ?? 0,
      quote_ts: prevMeta?.quote_ts ?? 0,
      frozen_at: prevMeta?.frozen_at ?? 0,
      source: prevMeta?.source ?? 'rest',
    },
  };
}

export function feedErrorFromPayload(data: { feed_error?: unknown }): string | null | undefined {
  if (!('feed_error' in data)) return undefined;
  const raw = data.feed_error;
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  return null;
}

/** One chip: subscriptionError > feed_error > unavailable > last-good. */
export function scannerHonestyChip(signals: HonestySignals): string | null {
  const sub = signals.subscriptionError?.trim();
  if (sub) return sub;
  const feed = signals.feedError?.trim();
  if (feed) return feed;
  if (signals.tableState === 'unavailable') return SCANNER_HONESTY_UNAVAILABLE;
  if (signals.lastGood) return SCANNER_HONESTY_LAST_GOOD;
  return null;
}

export function priceAgeChipText(opts: {
  lastPriceTs?: number | null;
  secondsAgo: number | null;
  pricesStale: boolean;
  formatAge: (seconds: number) => string;
}): string | null {
  if (opts.lastPriceTs === 0) return SCANNER_PRICE_NO_L1;
  if (opts.secondsAgo == null) return null;
  return opts.pricesStale
    ? `stale · ${opts.formatAge(opts.secondsAgo)}`
    : opts.formatAge(opts.secondsAgo);
}

export function showPriceAgeChip(opts: {
  historyDate: string | null;
  lastPriceTs?: number | null;
  secondsAgo: number | null;
}): boolean {
  if (opts.historyDate) return false;
  return opts.lastPriceTs != null || opts.secondsAgo != null;
}

export function tableHonestyLabel(
  meta: ScannerTableMeta | null | undefined,
  lastGood?: boolean,
): { text: string; kind: 'frozen' | 'honesty' } | null {
  const fromMeta = frozenTableLabel(meta);
  if (fromMeta) {
    return { text: fromMeta, kind: meta?.state === 'frozen' ? 'frozen' : 'honesty' };
  }
  if (lastGood) {
    return { text: SCANNER_HONESTY_LAST_GOOD_LABEL, kind: 'honesty' };
  }
  return null;
}

export function catalystsEmptyCopy(opts: {
  fetchError?: string | null;
  healthStatus: string;
  healthMessage?: string | null;
}): string {
  if (opts.fetchError?.trim()) return opts.fetchError.trim();
  if (opts.healthStatus === 'disconnected' || opts.healthStatus === 'error') {
    return opts.healthMessage?.trim() || SCANNER_CATALYSTS_FEED_DOWN;
  }
  return SCANNER_CATALYSTS_EMPTY;
}

export function catalystsHttpError(status: number): string {
  return `Catalysts feed failed (HTTP ${status}).`;
}

export function historyLoadError(date: string): string {
  return `Could not load snapshot for ${date}.`;
}

/** One table's snapshot failed while others loaded (QA C51). */
export function historyTableLoadError(date: string, label: string): string {
  return `Could not load the ${label} snapshot for ${date}.`;
}
