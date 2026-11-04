/**
 * Every desk list of positions shows both books (ADR 069 decision 9).
 *
 * `GET /api/ibkr/positions` on Paper is the shares yours to sell, and every Sell, Flatten, Cover, hotkey and the
 * ticket size from it: that never changes. A stock only the bots hold is missing from it, so the header said
 * Positions 0 beside the bots' working stops (operator report 2026-11-04). These rows are for reading: your rows as
 * they came, then one row per bot that holds shares. Nothing that sends an order may take them. No React, no fetch.
 */
import { OWNER_AUTO_ENTRY } from '../constantGroups/owners';
import type { PracticeAccount, PracticeOwnerHolding, PracticePosition } from '../practice';
import type { IbkrPosition } from './types';

export interface DeskPosition extends IbkrPosition {
  /** Paper only (ADR 069): absent on Live and Sim, where there is one book. */
  owner?: 'you' | 'bots';
  /** Which bot, by its orders' origin. On your row: Auto-entry, when the shares are its alone. */
  bot?: string | null;
  /** A bots' row: every bot's shares in this stock, signed -- what the Close on their row sells. */
  bots_qty?: number;
}

/** Auto-entry hands you its exit, so its shares already sit on your rows (backend `owners.books.yours`). */
const yoursToSell = (h: PracticeOwnerHolding): boolean => h.owner === 'you' || h.bot === OWNER_AUTO_ENTRY;

const heldIn = (account: PracticeAccount | null | undefined): PracticePosition[] =>
  Array.isArray(account?.positions) ? account.positions : [];

const key = (symbol: string): string => symbol.trim().toUpperCase();

/** Every bot's shares per stock, signed: the whole bots' book, Auto-entry's with the rest. */
export function botsBook(account: PracticeAccount | null | undefined): Map<string, number> {
  const out = new Map<string, number>();
  for (const p of heldIn(account)) {
    for (const h of p.by_owner ?? []) {
      if (h.owner === 'bots') out.set(key(p.symbol), (out.get(key(p.symbol)) ?? 0) + h.qty);
    }
  }
  return out;
}

/** The Auto-entry name on your row when those shares are its alone, else null. */
function handedOver(row: PracticePosition | undefined): string | null {
  const mine = (row?.by_owner ?? []).filter(yoursToSell);
  return mine.length > 0 && mine.every((h) => h.bot === OWNER_AUTO_ENTRY) ? OWNER_AUTO_ENTRY : null;
}

/** Your rows and the bots', on Paper with its two books; anywhere else your rows, untouched. */
export function deskPositions(yours: IbkrPosition[], account: PracticeAccount | null | undefined): DeskPosition[] {
  if (!account?.books) return yours;
  const held = heldIn(account);
  const bySymbol = new Map(held.map((p) => [key(p.symbol), p]));
  const rows: DeskPosition[] = yours.map((p) => ({ ...p, owner: 'you', bot: handedOver(bySymbol.get(key(p.symbol))) }));
  const book = botsBook(account);
  for (const p of held) {
    for (const h of p.by_owner ?? []) {
      if (yoursToSell(h) || h.qty === 0) continue;
      rows.push({
        symbol: key(p.symbol),
        qty: h.qty,
        avg_cost: h.avg_cost,
        market_price: p.mark,
        market_value: p.mark == null ? null : h.qty * p.mark,
        unrealized_pnl: h.unrealized_pnl,
        realized_pnl: null,
        position_side: h.qty < 0 ? 'short' : 'long',
        owner: 'bots',
        bot: h.bot,
        bots_qty: book.get(key(p.symbol)),
      });
    }
  }
  return rows;
}

/** One stock's bots' rows, in the order they came. */
export function botsRowsFor(rows: readonly DeskPosition[], symbol: string): DeskPosition[] {
  const needle = key(symbol);
  return rows.filter((p) => p.owner === 'bots' && key(p.symbol) === needle);
}
