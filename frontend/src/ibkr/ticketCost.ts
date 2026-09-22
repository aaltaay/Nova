/**
 * The compact ticket's `Cost $x · BP after $y` line (approved redesign,
 * 2026-09-21). A pure estimate from what the ticket already knows: the share
 * count the order would carry (the same `resolveOrderQuantity` the Place path
 * uses) times the order's own reference price, and buying power minus that.
 * Anything Nova cannot work out yet is null -- the line shows a dash, never a
 * guess -- and an order the door would refuse is priced at nothing: a SELL
 * only ever reduces a held long (Invariant #7; `OVERSELL`, `PRACTICE_NO_SHORTS`),
 * so a SELL from flat or past the held quantity frees no buying power, and a
 * practice venue refuses every short entry (QA 2026-09-22, V24).
 */
import { PRACTICE_NO_SHORTS_REASON } from '../constantGroups/practice';
import { TICKET_COST_NO_POSITION } from '../constantGroups/trader_chrome';
import {
  resolveOrderQuantity,
  type ManualOrderValues,
  type QuantityContext,
  type ResolveQuantityOptions,
} from './orderEntry';

export interface TicketCostEstimate {
  shares: number | null;
  price: number | null;
  cost: number | null;
  buyingPowerAfter: number | null;
  /** Why the line is a dash when Nova knows why (the line's tooltip). */
  note?: string | null;
}

export interface TicketCostVenue {
  /** Paper / Sim: Nova's practice broker, which refuses every short entry. */
  practice?: boolean;
  /** Why there is no market reference price on this venue right now, if that is known. */
  priceNote?: string | null;
}

const UNKNOWN: TicketCostEstimate = {
  shares: null,
  price: null,
  cost: null,
  buyingPowerAfter: null,
};

export function estimateTicketCost(
  values: ManualOrderValues,
  context: QuantityContext,
  options?: ResolveQuantityOptions,
  venue: TicketCostVenue = {},
): TicketCostEstimate {
  const resolved = resolveOrderQuantity(values, context, options);
  if ('error' in resolved) return UNKNOWN;
  const { quantity, referencePrice } = resolved;
  const shares = quantity > 0 ? quantity : null;
  if (venue.practice && values.shortEntry) return { ...UNKNOWN, shares, note: PRACTICE_NO_SHORTS_REASON };
  if (values.side === 'SELL' && !values.shortEntry) {
    const held = context.positionQty;
    if (held == null || !(held > 0) || (shares != null && shares > held)) {
      return { ...UNKNOWN, shares, note: TICKET_COST_NO_POSITION };
    }
  }
  if (referencePrice == null || !(quantity > 0)) {
    return { ...UNKNOWN, shares, note: referencePrice == null ? venue.priceNote ?? null : null };
  }
  const cost = quantity * referencePrice;
  const bp = context.buyingPower;
  // A buy or a short entry consumes buying power; a sell of a held long frees it.
  const consumes = values.side === 'BUY' || Boolean(values.shortEntry);
  const buyingPowerAfter =
    bp == null || !Number.isFinite(bp) ? null : consumes ? bp - cost : bp + cost;
  return { shares: quantity, price: referencePrice, cost, buyingPowerAfter };
}
