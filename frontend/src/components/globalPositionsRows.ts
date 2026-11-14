/**
 * Pure rows behind the header's Positions count and card: every stock the
 * venue's account holds now, one row per symbol and holder (ADR 072: on Paper
 * and Sim yours -- with any shares handed to you -- then Claude's, the brain's
 * and each retired bot's, long or short). A zero or unreadable quantity is not
 * a position. No React, no fetch.
 */
import { OWNERS, type Owner } from '../constantGroups/owners';
import type { DeskPosition } from '../ibkr/deskPositions';

export interface HeldPositionRow {
  symbol: string;
  /** Signed shares: negative is a short. */
  qty: number;
  avgCost: number | null;
  /** Null while the venue has no price for it -- never a fabricated zero. */
  openPnl: number | null;
  /** Whose shares, on Paper and Sim; absent on Live, where there is one book. */
  owner?: Owner;
  bot?: string | null;
  /** Your row: how many of its shares were handed to you, and by whom. */
  handed_qty?: number | null;
  handed_from?: DeskPosition['handed_from'];
}

const finite = (n: number | null | undefined): number | null =>
  n == null || !Number.isFinite(n) ? null : n;

/** Each stock's rows in the order every split reads them: yours, Claude's, the brain's, Earlier bots'. */
const bookOrder = (row: HeldPositionRow): number => (row.owner ? OWNERS.indexOf(row.owner) : 0);

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
        handed_qty: p.handed_qty, handed_from: p.handed_from,
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
    .sort((a, b) => a.symbol.localeCompare(b.symbol) || bookOrder(a) - bookOrder(b));
}
