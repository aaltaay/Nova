/**
 * The compact ticket's `Cost $x · BP after $y` line (approved redesign,
 * 2026-09-21). A pure estimate from what the ticket already knows: the share
 * count the order would carry (the same `resolveOrderQuantity` the Place path
 * uses) times the order's own reference price, and buying power minus that.
 * Anything Nova cannot work out yet is null -- the line shows a dash, never a
 * guess.
 */
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
): TicketCostEstimate {
  const resolved = resolveOrderQuantity(values, context, options);
  if ('error' in resolved) return UNKNOWN;
  const { quantity, referencePrice } = resolved;
  if (referencePrice == null || !(quantity > 0)) {
    return { ...UNKNOWN, shares: quantity > 0 ? quantity : null };
  }
  const cost = quantity * referencePrice;
  const bp = context.buyingPower;
  // A buy or a short entry consumes buying power; a sell of a held long frees it.
  const consumes = values.side === 'BUY' || Boolean(values.shortEntry);
  const buyingPowerAfter =
    bp == null || !Number.isFinite(bp) ? null : consumes ? bp - cost : bp + cost;
  return { shares: quantity, price: referencePrice, cost, buyingPowerAfter };
}
