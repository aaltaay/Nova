/**
 * Pure row mapping for the Desk board: the live scanner feed the workspace
 * already holds, condensed to the columns that matter beside the charts.
 * Lists the feed does not carry are a stated absence (null), never an empty
 * table; a missing figure stays null, never 0.
 */
import { DESK_REL_VOL_SUFFIX, DESK_CELL_ABSENT } from '../constantGroups/desk';
import type { LiveScannerFeed } from '../scanner/ScannerDataContext';
import { SCANNER_QUOTE_CLOSE_FALLBACK } from '../scanner/scannerRowShape';
import { catalystChipLabel, catalystFor, fractionToPercent } from '../stock_view/tabContext';
import { formatCoverageClockEt } from '../tickerChartData';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';

export interface DeskBoardRow {
  symbol: string;
  price: number | null;
  /** Signed gap in percent points (the row's fraction x100; falls back to the day change). */
  gapPct: number | null;
  volume: number | null;
  relVolume: number | null;
  float: number | null;
  /** NEWS / PR chip, null when the symbol has no known catalyst. */
  catalyst: string | null;
  headline: string | null;
  headlineSource: string | null;
  /** ISO stamp of the newest headline the feed knows, text or not. */
  headlineAt: string | null;
  /** Halt state: the scanner rows do not carry one, so this is a stated absence. */
  state: null;
}

export interface DeskBoardList {
  rows: DeskBoardRow[];
  /** Rows the feed holds for this list before any client-side filter. */
  total: number;
}

type FeedRows = Pick<LiveScannerFeed, 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'catalysts'>;

/** Lists the board can mirror from the feed it already has; others say so. */
export const DESK_BOARD_MIRRORED_LISTS: readonly string[] = [
  'gappers', 'gainers', 'losers', 'afterhours', 'large_cap', 'catalysts',
];

function finite(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function fromScannerRow(row: ScannerRow, catalysts: readonly Catalyst[]): DeskBoardRow {
  const catalyst = catalystFor(row.symbol, catalysts);
  // IB's prior close as the price (no print yet): its 0.0% gap is invented (QA W12).
  const closeFallback = row.quote_quality === SCANNER_QUOTE_CLOSE_FALLBACK;
  return {
    symbol: row.symbol.toUpperCase(),
    price: finite(row.price),
    gapPct: closeFallback ? null : fractionToPercent(row.gap_percent ?? row.change_pct),
    volume: finite(row.volume),
    relVolume: finite(row.rel_volume ?? row.rvol),
    float: finite(row.float),
    catalyst: catalystChipLabel(catalyst, row),
    headline: catalyst?.catalyst_headline ?? null,
    headlineSource: catalyst?.catalyst_source ?? null,
    headlineAt: row.newest_headline_at ?? catalyst?.newest_headline_at ?? null,
    state: null,
  };
}

function fromCatalyst(row: Catalyst): DeskBoardRow {
  return {
    symbol: row.symbol.toUpperCase(),
    price: finite(row.current_price),
    gapPct: fractionToPercent(row.gap_percent),
    volume: finite(row.volume),
    relVolume: null,
    float: null,
    catalyst: catalystChipLabel(row, null),
    headline: row.catalyst_headline,
    headlineSource: row.catalyst_source ?? null,
    headlineAt: row.newest_headline_at,
    state: null,
  };
}

/** Rows for a list id; null when the feed does not carry that list here. */
export function deskBoardRowsFor(
  list: string,
  feed: FeedRows | null | undefined,
  filterRows?: <T extends ScannerRow>(rows: T[]) => T[],
): DeskBoardList | null {
  if (!feed) return null;
  const pick = (rows: ScannerRow[]): DeskBoardList => ({
    rows: (filterRows ? filterRows(rows) : rows).map(row => fromScannerRow(row, feed.catalysts)),
    total: rows.length,
  });
  switch (list) {
    case 'gappers': return pick(feed.gappers);
    case 'gainers': return pick(feed.gainers);
    case 'losers': return pick(feed.losers);
    case 'afterhours': return pick(feed.afterhours);
    case 'large_cap': return pick(feed.largeCap);
    case 'catalysts': return { rows: feed.catalysts.map(fromCatalyst), total: feed.catalysts.length };
    default: return null;
  }
}

export interface DeskHeadline {
  /** HH:MM Eastern of the newest headline, null when the stamp is unusable. */
  clock: string | null;
  /** Headline text when the catalysts feed carries it; null when only the stamp is known. */
  text: string | null;
  source: string | null;
}

/**
 * The selected symbol's newest headline from the scanner news already
 * published per symbol: text from the catalysts list, otherwise the stamp a
 * scanner row carries. Null when no list knows the symbol.
 */
export function deskHeadlineFor(symbol: string | null, feed: FeedRows | null | undefined): DeskHeadline | null {
  if (!symbol || !feed) return null;
  const key = symbol.trim().toUpperCase();
  const catalyst = catalystFor(key, feed.catalysts);
  if (catalyst && (catalyst.catalyst_headline || catalyst.newest_headline_at)) {
    return {
      clock: formatCoverageClockEt(catalyst.newest_headline_at),
      text: catalyst.catalyst_headline,
      source: catalyst.catalyst_source ?? null,
    };
  }
  for (const rows of [feed.gappers, feed.gainers, feed.losers, feed.afterhours, feed.largeCap]) {
    const row = rows.find(r => r.symbol.toUpperCase() === key);
    if (!row) continue;
    if (!row.newest_headline_at) return { clock: null, text: null, source: null };
    return { clock: formatCoverageClockEt(row.newest_headline_at), text: null, source: null };
  }
  return null;
}

/** Bar width (0-100) of a row's |gap| against the widest gap on the board. */
export function gapBarPct(gapPct: number | null, maxAbsGap: number): number {
  if (gapPct == null || !(maxAbsGap > 0)) return 0;
  return Math.max(0, Math.min(100, Math.round((Math.abs(gapPct) / maxAbsGap) * 100)));
}

export function maxAbsGap(rows: readonly DeskBoardRow[]): number {
  return rows.reduce((max, row) => (row.gapPct != null ? Math.max(max, Math.abs(row.gapPct)) : max), 0);
}

/** "6.4×"; unknown stays a dash, never 0.0×. */
export function fmtRelVol(value: number | null): string {
  if (value == null) return DESK_CELL_ABSENT;
  // A real ratio that prints as 0.0 reads "<0.1x", never "0.0x" (QA W22).
  if (value < 0.05) return `<0.1${DESK_REL_VOL_SUFFIX}`;
  return `${value.toFixed(1)}${DESK_REL_VOL_SUFFIX}`;
}

/** HH:MM Eastern for a headline stamp; null when the stamp is unusable. */
export const headlineClockEt = formatCoverageClockEt;
