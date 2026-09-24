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
 *
 * A Market order is priced where it fills -- the far side of a known quote,
 * the ask to buy and the bid to sell -- not the last (QA R36). On a practice
 * venue "BP after" follows the ledger's own rule (fees out of equity, the
 * position re-marked at the fill, 4x, 1x under $2,000), not BP +/- the order value (W28).
 */
import { PRACTICE_NO_SHORTS_REASON } from '../constantGroups/practice';
import { TICKET_COST_NO_POSITION } from '../constantGroups/trader_chrome';
import { practiceBuyingPowerAfter } from '../practice/practiceBuyingPower';
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
  /** Where a Market order fills: the far side of a known quote (R36); null prices it at the reference. */
  marketFillPrice?: number | null;
  /** Practice ledger figures for the exact BP-after rule (W28); absent falls back to BP +/- cost. */
  ledger?: {
    netLiquidation: number | null;
    grossPositionValue: number | null;
    heldMark: number | null;
  } | null;
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
  // The share count is the Place path's (from the reference); only the price
  // a Market order fills at moves to the far side of the quote (R36).
  const fill = values.orderType === 'MKT' && venue.marketFillPrice != null && venue.marketFillPrice > 0
    ? venue.marketFillPrice
    : referencePrice;
  const cost = quantity * fill;
  const bp = context.buyingPower;
  // A buy or a short entry consumes buying power; a sell of a held long frees it.
  const consumes = values.side === 'BUY' || Boolean(values.shortEntry);
  const ledgerBp = venue.practice && venue.ledger
    ? practiceBuyingPowerAfter({
        netLiquidation: venue.ledger.netLiquidation,
        grossPositionValue: venue.ledger.grossPositionValue,
        side: values.side,
        qty: quantity,
        price: fill,
        heldQty: context.positionQty ?? 0,
        heldMark: venue.ledger.heldMark,
      })
    : null;
  const buyingPowerAfter = ledgerBp
    ?? (bp == null || !Number.isFinite(bp) ? null : consumes ? bp - cost : bp + cost);
  return { shares: quantity, price: fill, cost, buyingPowerAfter };
}
