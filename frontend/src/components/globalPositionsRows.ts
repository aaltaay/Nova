/**
 * Pure rows behind the header's Positions count and card: every stock the
 * venue's account holds now, one row per symbol and holder (ADR 069 decision 9:
 * on Paper yours and each bot's, long or short). A zero or unreadable quantity
 * is not a position. No React, no fetch.
 */
import type { DeskPosition } from '../ibkr/deskPositions';

export interface HeldPositionRow {
  symbol: string;
  /** Signed shares: negative is a short. */
  qty: number;
  avgCost: number | null;
  /** Null while the venue has no price for it -- never a fabricated zero. */
  openPnl: number | null;
  /** Whose shares, on Paper; absent where there is one book. */
  owner?: 'you' | 'bots';
  bot?: string | null;
}

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

const yoursFirst = (row: HeldPositionRow): number => (row.owner === 'bots' ? 1 : 0);

export function heldPositionRows(positions: readonly DeskPosition[]): HeldPositionRow[] {
  const byHolder = new Map<string, HeldPositionRow>();
  for (const p of positions) {
    const symbol = p.symbol?.trim().toUpperCase();
    if (!symbol || !Number.isFinite(p.qty) || p.qty === 0) continue;
    const holder = `${symbol}|${p.owner ?? ''}|${p.bot ?? ''}`;
    const have = byHolder.get(holder);
    if (!have) {
      byHolder.set(holder, {
        symbol, qty: p.qty, avgCost: finite(p.avg_cost), openPnl: finite(p.unrealized_pnl), owner: p.owner, bot: p.bot,
      });
      continue;
    }
    // Two rows for one holder of one symbol: the shares add, and the open P&L is known only when both are.
    const pnl = finite(p.unrealized_pnl);
    have.qty += p.qty;
    have.avgCost = null;
    have.openPnl = have.openPnl == null || pnl == null ? null : have.openPnl + pnl;
  }
  return [...byHolder.values()]
    .filter((r) => r.qty !== 0)
    .sort((a, b) => a.symbol.localeCompare(b.symbol) || yoursFirst(a) - yoursFirst(b));
}
