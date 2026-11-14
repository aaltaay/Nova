/**
 * Every desk list of positions reads every book (ADR 072, architecture/schema/recording-and-replay.md, "Three
 * traders' books").
 *
 * `GET /api/ibkr/positions` on Paper and Sim is the shares yours to close -- your own plus any handed to you
 * (`handed_qty`, `handed_from`) -- and every Sell, Flatten, Cover, hotkey and the ticket size from it: that never
 * changes. A stock only another trader holds is missing from it. These rows are for reading: your rows as they came,
 * then one row per other holder (Claude, the brain, a retired bot) from `by_owner[]` of `/api/practice/account`,
 * each valued at the position's mark. Shares handed to you are already on your row, so they are never listed twice.
 * Nothing that sends an order may take another trader's row. No React, no fetch.
 */
import { OWNERS, type Owner } from '../constantGroups/owners';
import type { PracticeAccount, PracticeOwnerHolding, PracticePosition } from '../practice';
import type { IbkrPosition } from './types';

export interface DeskPosition extends IbkrPosition {
  /** Paper and Sim (ADR 072): whose row it is; absent on Live, where every row is yours. */
  owner?: Owner;
  /** The retired bot, on an Earlier bots' row. */
  bot?: string | null;
}

/** One trader's shares in a stock, signed: for a refusal's words, never what an order sizes from. */
export interface OwnerHold {
  owner: Owner;
  qty: number;
}

/** Another trader's own shares: not yours, and not handed to you (those sit on your row). */
const othersOwn = (h: PracticeOwnerHolding): boolean => h.owner !== 'you' && h.handed !== true && h.qty !== 0;

const heldIn = (account: PracticeAccount | null | undefined): PracticePosition[] =>
  Array.isArray(account?.positions) ? account.positions : [];

const key = (symbol: string): string => symbol.trim().toUpperCase();

/** Each stock's other traders and their shares, signed, the biggest holder first. */
export function othersBook(account: PracticeAccount | null | undefined): Map<string, OwnerHold[]> {
  const out = new Map<string, OwnerHold[]>();
  for (const p of heldIn(account)) {
    const byOwner = new Map<Owner, number>();
    for (const h of p.by_owner ?? []) {
      if (othersOwn(h)) byOwner.set(h.owner, (byOwner.get(h.owner) ?? 0) + h.qty);
    }
    const holds = OWNERS.filter((o) => (byOwner.get(o) ?? 0) !== 0).map((owner) => ({ owner, qty: byOwner.get(owner) ?? 0 }));
    if (holds.length) out.set(key(p.symbol), holds.sort((a, b) => Math.abs(b.qty) - Math.abs(a.qty)));
  }
  return out;
}

/** Your rows and every other holder's, where the account keeps books; anywhere else your rows, untouched. */
export function deskPositions(yours: IbkrPosition[], account: PracticeAccount | null | undefined): DeskPosition[] {
  if (!account?.books) return yours;
  const rows: DeskPosition[] = yours.map((p) => ({ ...p, owner: 'you', bot: null }));
  for (const p of heldIn(account)) {
    for (const h of (p.by_owner ?? []).filter(othersOwn)) {
      rows.push({
        symbol: key(p.symbol),
        qty: h.qty,
        avg_cost: h.avg_cost,
        market_price: p.mark,
        market_value: p.mark == null ? null : h.qty * p.mark,
        unrealized_pnl: h.unrealized_pnl,
        realized_pnl: null,
        position_side: h.qty < 0 ? 'short' : 'long',
        owner: h.owner,
        bot: h.bot,
      });
    }
  }
  return rows;
}

/** True for a row another trader holds: you never close or size from it. */
export const isOthersRow = (p: Pick<DeskPosition, 'owner'>): boolean => p.owner != null && p.owner !== 'you';

/** One stock's other traders' rows, in the order they came. */
export function othersRowsFor(rows: readonly DeskPosition[], symbol: string): DeskPosition[] {
  const needle = key(symbol);
  return rows.filter((p) => isOthersRow(p) && key(p.symbol) === needle);
}

/** Your own shares on your row (the handed ones apart); 0 when every share there was handed to you. */
export function ownShares(p: Pick<DeskPosition, 'qty' | 'handed_qty'>): number {
  return p.qty - (p.handed_qty ?? 0);
}
