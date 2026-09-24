/**
 * One shape gate for every scanner row that reaches the desk -- REST tables,
 * /ws/scanner roster snapshots, history snapshots and price patches.
 *
 * The rows used to be cast (`incoming as T[]`) and trusted: one row with a
 * null symbol, a price sent as a string, an exchange sent as an object or a
 * short ratio of "Infinity" crashed the Scanner view (QA C8), and a price
 * patch with `symbol: null` replaced the whole desk from inside a React state
 * updater (QA C5). Here a row without a usable symbol is dropped, a number
 * that is not finite becomes null (a stated absence, never a guess or a 0),
 * and text fields that are not text become null.
 *
 * Pure: no module state.
 */
import type { ScannerPricePatchRow } from '../hooks/useScannerPriceStream';
import { applyScannerPricePatch } from '../hooks/useScannerPriceStream';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';
import { normalizeCatalystVerdict } from '../utils/catalystVerdict';

/** Numeric fields every row carries (null when unknown). */
const ROW_NUMBERS = [
  'price',
  'prev_close',
  'change_pct',
  'change_abs',
  'gap_percent',
  'volume',
  'rel_volume',
  'market_cap',
  'float',
  'short_interest',
  'short_ratio',
] as const;

/** Numeric fields only some tables carry -- left absent when the row has none. */
const OPTIONAL_ROW_NUMBERS = [
  'rank',
  'current_price',
  'previous_close',
  'open',
  'earnings_day_offset',
  'watchlist_score',
  'rvol',
  'atr_expansion',
  'change_5d_pct',
  'change_20d_pct',
  'high_20d',
  'low_20d',
  'large_cap_score',
  'score_completeness',
  'days_to_earnings',
  'shares_outstanding',
  'short_interest_ts',
] as const;

/** Numeric fields a /ws/scanner price_patch row may carry. */
const PATCH_NUMBERS = [
  'price',
  'change_pct',
  'change_abs',
  'volume',
  'gap_percent',
  'quote_ts',
  'rvol',
  'atr_expansion',
  'change_5d_pct',
  'change_20d_pct',
  'high_20d',
  'low_20d',
  'days_to_earnings',
  'market_cap',
  'float',
] as const;

const EARNINGS_SESSIONS = new Set(['bmo', 'amc', 'intraday']);

/** IBKR sent no last trade, so the price is the prior close (ibkr/ticks_handler.py). */
export const SCANNER_QUOTE_CLOSE_FALLBACK = 'close_fallback';

/** A price-patch row plus the quote quality the backend stamps on it. */
export type HonestPatchRow = ScannerPricePatchRow & { quote_quality?: string | null };

export function finiteOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function textOrNull(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function symbolOf(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().toUpperCase() : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * True when the row has no quote at all -- a name the roster admitted before
 * its first L1 tick (ADR 010 decision 5). Its figures are absences.
 */
export function isNameOnlyRow(row: Pick<ScannerRow, 'price'> & { current_price?: number | null }): boolean {
  return finiteOrNull(row.price) == null && finiteOrNull(row.current_price) == null;
}

/** One row, or null when it has no usable symbol. Unknown extra fields pass through. */
export function normalizeScannerRow(raw: unknown): ScannerRow | null {
  if (!isRecord(raw)) return null;
  const symbol = symbolOf(raw.symbol);
  if (!symbol) return null;
  const out: Record<string, unknown> = { ...raw, symbol };
  for (const key of ROW_NUMBERS) out[key] = finiteOrNull(raw[key]);
  for (const key of OPTIONAL_ROW_NUMBERS) {
    if (key in raw) out[key] = finiteOrNull(raw[key]);
  }
  out.exchange = textOrNull(raw.exchange);
  out.newest_headline_at = textOrNull(raw.newest_headline_at);
  out.has_news = raw.has_news === true;
  // Present (object or null) only from a backend that reads catalysts; absent keeps the headline flame.
  if ('catalyst' in raw) out.catalyst = normalizeCatalystVerdict(raw.catalyst);
  if ('earnings_date' in raw) out.earnings_date = textOrNull(raw.earnings_date);
  if ('earnings_session' in raw) {
    out.earnings_session = EARNINGS_SESSIONS.has(raw.earnings_session as string)
      ? raw.earnings_session
      : null;
  }
  if ('earnings_estimated' in raw) {
    out.earnings_estimated = typeof raw.earnings_estimated === 'boolean' ? raw.earnings_estimated : null;
  }
  if ('quote_quality' in raw) out.quote_quality = textOrNull(raw.quote_quality);
  if ('rvol_source' in raw) out.rvol_source = textOrNull(raw.rvol_source);
  // #487: only a real true / false is a stated halt; anything else is "not known".
  if ('halted' in raw) out.halted = typeof raw.halted === 'boolean' ? raw.halted : null;
  // #532: only a real true / false is a checked float; anything else is "not checkable".
  if ('float_contradicted' in raw) {
    out.float_contradicted = typeof raw.float_contradicted === 'boolean' ? raw.float_contradicted : null;
  }
  if ('float_contradicted_reason' in raw) out.float_contradicted_reason = textOrNull(raw.float_contradicted_reason);
  // A name-only row carries a placeholder volume of 0 (ibkr/scanner_hydrate.py);
  // with no quote it is unknown, not zero (QA C37).
  if (out.volume === 0 && isNameOnlyRow(out as Pick<ScannerRow, 'price'>)) out.volume = null;
  return out as unknown as ScannerRow;
}

/** A table of rows, or null when the payload is not a list (the caller keeps what it has). */
export function normalizeScannerRows(raw: unknown): ScannerRow[] | null {
  if (!Array.isArray(raw)) return null;
  const out: ScannerRow[] = [];
  for (const item of raw) {
    const row = normalizeScannerRow(item);
    if (row) out.push(row);
  }
  return out;
}

/**
 * Price-patch rows: a row without a symbol is skipped; a field that is present
 * but not a finite number becomes null (for price / change / volume / gap that
 * means "no update"; for the Large Cap fields it is an explicit unknown).
 */
export function normalizePatchRows(raw: unknown): HonestPatchRow[] {
  if (!Array.isArray(raw)) return [];
  const out: HonestPatchRow[] = [];
  for (const item of raw) {
    if (!isRecord(item)) continue;
    const symbol = symbolOf(item.symbol);
    if (!symbol) continue;
    const row: Record<string, unknown> = { symbol };
    for (const key of PATCH_NUMBERS) {
      if (key in item) row[key] = finiteOrNull(item[key]);
    }
    if ('quote_quality' in item) row.quote_quality = textOrNull(item.quote_quality);
    out.push(row as HonestPatchRow);
  }
  return out;
}

/**
 * Merge normalized patch rows and carry each patched price's quote quality
 * onto its row: a prior-close fallback must never read as a live trade (QA C50).
 * A patch without a price leaves the row's quality as it was.
 */
export function applyHonestPricePatch<T extends ScannerRow>(
  rows: T[],
  patch: HonestPatchRow[],
): T[] {
  const next = applyScannerPricePatch(rows, patch);
  const quality = new Map<string, string | null>();
  for (const p of patch) {
    if (p.price == null) continue;
    quality.set(p.symbol, p.quote_quality ?? null);
  }
  if (quality.size === 0) return next;
  let changed = false;
  const stamped = next.map((row) => {
    const key = row.symbol.toUpperCase();
    if (!quality.has(key)) return row;
    const q = quality.get(key) ?? null;
    if ((row.quote_quality ?? null) === q) return row;
    changed = true;
    return { ...row, quote_quality: q };
  });
  return changed ? stamped : next;
}

/**
 * A roster/REST replace carries no quote quality (the cache row never stores
 * it). Keep a prior-close mark on a row whose price did not move since the
 * patch that marked it, so a membership refresh cannot relabel the prior
 * close as a live trade.
 */
export function carryQuoteQuality<T extends ScannerRow>(prev: readonly T[], next: T[]): T[] {
  if (prev.length === 0 || next.length === 0) return next;
  const marked = new Map<string, number | null>();
  for (const row of prev) {
    if (row.quote_quality === SCANNER_QUOTE_CLOSE_FALLBACK) marked.set(row.symbol, row.price);
  }
  if (marked.size === 0) return next;
  let changed = false;
  const out = next.map((row) => {
    if ('quote_quality' in row || !marked.has(row.symbol)) return row;
    if (marked.get(row.symbol) !== row.price) return row;
    changed = true;
    return { ...row, quote_quality: SCANNER_QUOTE_CLOSE_FALLBACK };
  });
  return changed ? out : next;
}

/** Catalyst rows: drop a row without a symbol and keep `exchange` text-only. */
export function normalizeCatalystRows(raw: unknown): Catalyst[] | null {
  if (!Array.isArray(raw)) return null;
  const out: Catalyst[] = [];
  for (const item of raw) {
    if (!isRecord(item)) continue;
    const symbol = symbolOf(item.symbol);
    if (!symbol) continue;
    out.push({ ...item, symbol, exchange: textOrNull(item.exchange) } as unknown as Catalyst);
  }
  return out;
}
