/**
 * One position shape whichever account is THE account on the venue: the
 * practice ledger's rows on Paper / Sim, IBKR's on Live. Pure.
 */
import type { Owner } from '../constantGroups/owners';
import type { IbkrPosition } from '../ibkr';
import type { PracticePosition } from '../practice';

export interface AccountPosition {
  symbol: string;
  qty: number;
  avgCost: number | null;
  mark: number | null;
  marketValue: number | null;
  unrealized: number | null;
  /** Practice marks are Nova's estimates, never an IBKR quote. */
  estimated: boolean;
  /** Paper and Sim (ADR 072): whose shares the row is -- one row per holder; absent on Live. */
  owner?: Owner;
  bot?: string | null;
  /** These shares are handed to you: a switched-off trader's, or a retired bot's -- yours to close. */
  handed?: boolean;
}

const finite = (n: number | null | undefined): number | null =>
  typeof n !== 'number' || !Number.isFinite(n) ? null : n;

/**
 * Rows that can be shown: a list of objects that name a symbol with a numeric
 * quantity. A `positions: null` answer used to replace the Account page with
 * "Cannot read properties of null (reading 'map')" (QA C11).
 */
function usableRows<T extends { symbol: unknown; qty: unknown }>(rows: unknown): T[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter(
    (row): row is T =>
      row != null && typeof row === 'object' && typeof row.symbol === 'string' && finite(row.qty) != null,
  );
}

export function positionsFromPractice(rows: PracticePosition[] | null | undefined): AccountPosition[] {
  return usableRows<PracticePosition>(rows).map((row) => {
    const mark = finite(row.mark);
    return {
      symbol: row.symbol.toUpperCase(),
      qty: row.qty,
      avgCost: finite(row.avg_cost),
      mark,
      marketValue: mark == null ? null : row.qty * mark,
      unrealized: finite(row.unrealized),
      estimated: true,
    };
  });
}

/** Paper and Sim's rows as each holder's (ADR 072): one row per holder -- you, Claude, the brain, a retired bot --
 *  each at its own cost and its own size; nothing on one row sizes from another's. A row with no holders (an older
 *  backend) stays as it is. */
export function positionsByOwner(rows: PracticePosition[] | null | undefined): AccountPosition[] {
  const valid = usableRows<PracticePosition>(rows);
  return positionsFromPractice(valid).flatMap((base, i) => {
    const holders = valid[i].by_owner;
    if (!Array.isArray(holders) || !holders.length) return [base];
    return holders.map((h) => ({
      ...base,
      qty: h.qty,
      avgCost: finite(h.avg_cost),
      marketValue: base.mark == null ? null : h.qty * base.mark,
      unrealized: finite(h.unrealized_pnl),
      owner: h.owner,
      bot: h.bot,
      handed: h.handed === true,
    }));
  });
}

/** Rows of one stock added up, one row per symbol (what the Symbol P&L table reads). */
export function positionsBySymbol(rows: AccountPosition[]): AccountPosition[] {
  const out = new Map<string, AccountPosition>();
  const add = (a: number | null, b: number | null): number | null => (a == null || b == null ? null : a + b);
  for (const row of rows) {
    const seen = out.get(row.symbol);
    if (!seen) {
      out.set(row.symbol, { ...row, owner: undefined, bot: undefined, handed: undefined });
      continue;
    }
    const qty = seen.qty + row.qty;
    const size = Math.abs(seen.qty) + Math.abs(row.qty);
    const avg = seen.avgCost != null && row.avgCost != null && size > 0
      ? (Math.abs(seen.qty) * seen.avgCost + Math.abs(row.qty) * row.avgCost) / size
      : null;
    out.set(row.symbol, { ...seen, qty, avgCost: avg, marketValue: add(seen.marketValue, row.marketValue),
                          unrealized: add(seen.unrealized, row.unrealized) });
  }
  return [...out.values()];
}

export function positionsFromIbkr(rows: IbkrPosition[] | null | undefined): AccountPosition[] {
  return usableRows<IbkrPosition>(rows).map((row) => ({
    symbol: row.symbol.toUpperCase(),
    qty: row.qty,
    avgCost: finite(row.avg_cost),
    mark: finite(row.market_price),
    marketValue: finite(row.market_value),
    unrealized: finite(row.unrealized_pnl),
    estimated: false,
  }));
}

/** Sum of long market values; null when a long position has no mark. */
export function longMarketValue(positions: AccountPosition[]): number | null {
  let sum = 0;
  for (const p of positions) {
    if (p.qty <= 0) continue;
    if (p.marketValue == null) return null;
    sum += p.marketValue;
  }
  return sum;
}

export function shortMarketValue(positions: AccountPosition[]): number | null {
  let sum = 0;
  let any = false;
  for (const p of positions) {
    if (p.qty >= 0) continue;
    any = true;
    if (p.marketValue == null) return null;
    sum += Math.abs(p.marketValue);
  }
  return any ? sum : null;
}

/** The largest open position by share count, of every source; null when flat (QA W11). */
export function largestPosition(positions: AccountPosition[]): { symbol: string; qty: number } | null {
  let best: { symbol: string; qty: number } | null = null;
  for (const p of positions) {
    const qty = Math.abs(p.qty);
    if (qty > 0 && (best == null || qty > best.qty)) best = { symbol: p.symbol, qty };
  }
  return best;
}

export const positionSymbols = (positions: AccountPosition[]): string[] =>
  positions.filter((p) => p.qty !== 0).map((p) => p.symbol);
