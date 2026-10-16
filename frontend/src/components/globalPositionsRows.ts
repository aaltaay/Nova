/**
 * Pure rows behind the header's Positions count and card: every stock the
 * venue's account holds now, one row per symbol, long or short. A zero or
 * unreadable quantity is not a position. No React, no fetch.
 */
import type { IbkrPosition } from '../ibkr/types';

export interface HeldPositionRow {
  symbol: string;
  /** Signed shares: negative is a short. */
  qty: number;
  avgCost: number | null;
  /** Null while the venue has no price for it -- never a fabricated zero. */
  openPnl: number | null;
}

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

export function heldPositionRows(positions: readonly IbkrPosition[]): HeldPositionRow[] {
  const bySymbol = new Map<string, HeldPositionRow>();
  for (const p of positions) {
    const symbol = p.symbol?.trim().toUpperCase();
    if (!symbol || !Number.isFinite(p.qty) || p.qty === 0) continue;
    const have = bySymbol.get(symbol);
    if (!have) {
      bySymbol.set(symbol, { symbol, qty: p.qty, avgCost: finite(p.avg_cost), openPnl: finite(p.unrealized_pnl) });
      continue;
    }
    // Two rows for one symbol: the shares add, and the open P&L is known only when both are.
    const pnl = finite(p.unrealized_pnl);
    have.qty += p.qty;
    have.avgCost = null;
    have.openPnl = have.openPnl == null || pnl == null ? null : have.openPnl + pnl;
  }
  return [...bySymbol.values()].filter((r) => r.qty !== 0).sort((a, b) => a.symbol.localeCompare(b.symbol));
}
