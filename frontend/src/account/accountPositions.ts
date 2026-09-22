/**
 * One position shape whichever account is THE account on the venue: the
 * practice ledger's rows on Paper / Sim, IBKR's on Live. Pure.
 */
import type { IbkrPosition } from '../ibkr/types';
import type { PracticePosition } from '../practice/practiceTypes';

export interface AccountPosition {
  symbol: string;
  qty: number;
  avgCost: number | null;
  mark: number | null;
  marketValue: number | null;
  unrealized: number | null;
  /** Practice marks are Nova's estimates, never an IBKR quote. */
  estimated: boolean;
}

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

export function positionsFromPractice(rows: PracticePosition[]): AccountPosition[] {
  return rows.map((row) => {
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

export function positionsFromIbkr(rows: IbkrPosition[]): AccountPosition[] {
  return rows.map((row) => ({
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

export const maxPositionQty = (positions: AccountPosition[]): number =>
  positions.reduce((max, p) => Math.max(max, Math.abs(p.qty)), 0);

export const positionSymbols = (positions: AccountPosition[]): string[] =>
  positions.filter((p) => p.qty !== 0).map((p) => p.symbol);
