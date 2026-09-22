/**
 * What a symbol tab / Focus row says beside the name: the signed gap and a
 * catalyst chip, read from the scanner rows the workspace already holds.
 * Pure: unknown stays null, never 0.00 or an invented category.
 */
import {
  TRADER_CATALYST_NEWS,
  TRADER_CATALYST_PR,
  TRADER_CATALYST_PR_SOURCES,
} from '../constantGroups/trader_chrome';
import type { ScannerDockRows } from '../scanner/useScannerDockRows';
import type { Catalyst } from '../types/catalyst';
import type { ScannerRow } from '../types/scanner';

export interface TabContext {
  /** Signed gap in percent points, 156.49 for +156.49% (falls back to the day change when the row has no gap). */
  gapPct: number | null;
  /** Chip label (NEWS / PR) or null when the symbol has no known catalyst. */
  catalyst: string | null;
  /** Headline behind the chip, for the tooltip. */
  headline: string | null;
  /** True when a scanner row was found; a row with no news can then say "no news". */
  known: boolean;
  price: number | null;
}

const NO_CONTEXT: TabContext = { gapPct: null, catalyst: null, headline: null, known: false, price: null };

/**
 * Scanner rows and catalysts carry `gap_percent` / `change_pct` as fractions
 * (1.5649 = +156.49%); the tab, Focus rail and Desk board print percent
 * points. Reading the fraction as percent showed GRML "+1.6%" (QA V2 / C17).
 */
export function fractionToPercent(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value * 100 : null;
}

/** Search order mirrors the desk's own priority: gappers first. */
export function scannerRowFor(symbol: string, rows: Pick<ScannerDockRows, 'gappers' | 'gainers' | 'losers' | 'afterhours'> | null | undefined): ScannerRow | null {
  if (!rows) return null;
  const key = symbol.trim().toUpperCase();
  if (!key) return null;
  for (const list of [rows.gappers, rows.gainers, rows.losers, rows.afterhours]) {
    const hit = list.find(row => row.symbol.toUpperCase() === key);
    if (hit) return hit;
  }
  return null;
}

export function catalystFor(symbol: string, catalysts: readonly Catalyst[] | null | undefined): Catalyst | null {
  const key = symbol.trim().toUpperCase();
  return catalysts?.find(row => row.symbol.toUpperCase() === key) ?? null;
}

/** PR for a company wire, NEWS for anything else with a headline. */
export function catalystChipLabel(catalyst: Catalyst | null, row: ScannerRow | null): string | null {
  if (catalyst?.catalyst_headline || catalyst?.has_news) {
    const source = (catalyst.catalyst_source ?? '').toLowerCase();
    return TRADER_CATALYST_PR_SOURCES.some(wire => source.includes(wire))
      ? TRADER_CATALYST_PR
      : TRADER_CATALYST_NEWS;
  }
  if (row?.has_news) return TRADER_CATALYST_NEWS;
  return null;
}

export function tabContextFor(symbol: string, rows: ScannerDockRows | null | undefined): TabContext {
  const row = scannerRowFor(symbol, rows);
  const catalyst = catalystFor(symbol, rows?.catalysts);
  if (!row && !catalyst) return NO_CONTEXT;
  const gap = row?.gap_percent ?? row?.change_pct ?? catalyst?.gap_percent ?? null;
  return {
    gapPct: fractionToPercent(gap),
    catalyst: catalystChipLabel(catalyst, row),
    headline: catalyst?.catalyst_headline ?? null,
    known: true,
    price: row?.price ?? catalyst?.current_price ?? null,
  };
}

/** "+131%" above a hundred, "+14.6%" / "−5.4%" below; null stays empty; a
 * move that prints as 0.0% has no sign, never "−0.0%" (QA W21). */
export function formatSignedPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '';
  const abs = Math.abs(value);
  const digits = abs >= 100 ? 0 : 1;
  if (Number(abs.toFixed(digits)) === 0) return `${(0).toFixed(digits)}%`;
  const sign = value > 0 ? '+' : '−';
  return `${sign}${abs.toFixed(digits)}%`;
}

export function pctTone(value: number | null | undefined): 'up' | 'down' | 'flat' {
  if (value == null || !Number.isFinite(value) || Number(Math.abs(value).toFixed(1)) === 0) return 'flat';
  return value > 0 ? 'up' : 'down';
}

/** Inactive tabs carry the chip as one letter; the full label rides as the tooltip. */
export function catalystInitial(label: string): string {
  return label.trim().charAt(0).toUpperCase();
}
