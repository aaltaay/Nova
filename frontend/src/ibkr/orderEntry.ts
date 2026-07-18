import {
  TICKER_TRADE_DOLLAR_PRESETS,
  TICKER_TRADE_FORCE_QTY,
  TICKER_TRADE_PERCENT_PRESETS,
  TICKER_TRADE_QTY_DECIMALS,
  TICKER_TRADE_SHARE_PRESETS,
} from '../constants';

export type ManualOrderSide = 'BUY' | 'SELL';
export type ManualOrderType = 'MKT' | 'LMT' | 'STP';
export type QuantityMode = 'shares' | 'percent' | 'dollars';

export interface ManualOrderValues {
  symbol: string;
  side: ManualOrderSide;
  orderType: ManualOrderType;
  quantityMode: QuantityMode;
  quantityValue: string;
  limitPrice: string;
  stopPrice: string;
  outsideRth: boolean;
}

export interface QuantityContext {
  marketReferencePrice: number | null;
  buyingPower: number | null;
  positionQty: number | null;
}

export interface ManualOrderPayload {
  symbol: string;
  side: ManualOrderSide;
  qty: number;
  order_type: ManualOrderType;
  limit_price?: number;
  stop_price?: number;
  outside_rth: boolean;
}

export type BuildOrderResult =
  | { ok: true; payload: ManualOrderPayload; quantity: number; referencePrice: number | null }
  | { ok: false; error: string };

function positiveNumber(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function floorQuantity(quantity: number): number {
  const factor = 10 ** TICKER_TRADE_QTY_DECIMALS;
  return Math.floor((quantity + Number.EPSILON) * factor) / factor;
}

export function presetsForQuantityMode(mode: QuantityMode): readonly number[] {
  if (mode === 'percent') return TICKER_TRADE_PERCENT_PRESETS;
  if (mode === 'dollars') return TICKER_TRADE_DOLLAR_PRESETS;
  return TICKER_TRADE_SHARE_PRESETS;
}

export function orderReferencePrice(
  values: ManualOrderValues,
  marketReferencePrice: number | null,
): number | null {
  if (values.orderType === 'LMT') return positiveNumber(values.limitPrice);
  if (values.orderType === 'STP') return positiveNumber(values.stopPrice);
  return marketReferencePrice != null && marketReferencePrice > 0
    ? marketReferencePrice
    : null;
}

export interface ResolveQuantityOptions {
  /** Override `TICKER_TRADE_FORCE_QTY` (tests pass `null` to exercise free sizing). */
  forceQty?: number | null;
}

/** Effective forced share qty, or null when sizing is unlocked. */
export function forcedManualOrderQty(
  override?: number | null,
): number | null {
  const forceQty = override !== undefined ? override : TICKER_TRADE_FORCE_QTY;
  return forceQty != null && forceQty > 0 ? forceQty : null;
}

export function resolveOrderQuantity(
  values: ManualOrderValues,
  context: QuantityContext,
  options?: ResolveQuantityOptions,
): { quantity: number; referencePrice: number | null } | { error: string } {
  const referencePrice = orderReferencePrice(values, context.marketReferencePrice);
  const forced = forcedManualOrderQty(options?.forceQty);
  if (forced != null) {
    return { quantity: forced, referencePrice };
  }

  const amount = positiveNumber(values.quantityValue);
  if (amount == null) return { error: 'Enter a valid quantity' };

  if (values.quantityMode === 'shares') {
    return { quantity: amount, referencePrice };
  }
  if (referencePrice == null) {
    return { error: 'A current or order price is required for this quantity mode' };
  }

  if (values.quantityMode === 'dollars') {
    const quantity = floorQuantity(amount / referencePrice);
    return quantity > 0
      ? { quantity, referencePrice }
      : { error: 'Dollar amount is too small for the reference price' };
  }

  if (amount > 100) return { error: 'Percentage quantity cannot exceed 100%' };
  if (values.side === 'BUY') {
    if (context.buyingPower == null || context.buyingPower <= 0) {
      return { error: 'Buying Power is required for percentage buys' };
    }
    const quantity = floorQuantity(
      ((context.buyingPower * amount) / 100) / referencePrice,
    );
    return quantity > 0
      ? { quantity, referencePrice }
      : { error: 'Percentage amount is too small for the reference price' };
  }

  if (context.positionQty == null || context.positionQty <= 0) {
    return { error: 'A long position is required for percentage sells' };
  }
  const quantity = floorQuantity((context.positionQty * amount) / 100);
  return quantity > 0
    ? { quantity, referencePrice }
    : { error: 'Percentage amount is too small for the current position' };
}

export function buildManualOrder(
  values: ManualOrderValues,
  context: QuantityContext,
  options?: ResolveQuantityOptions,
): BuildOrderResult {
  const symbol = values.symbol.trim().toUpperCase();
  if (!symbol) return { ok: false, error: 'Symbol is required' };
  if (values.outsideRth && values.orderType !== 'LMT') {
    return { ok: false, error: 'Extended hours supports Limit orders only' };
  }

  const quantityResult = resolveOrderQuantity(values, context, options);
  if ('error' in quantityResult) {
    return { ok: false, error: quantityResult.error };
  }

  const payload: ManualOrderPayload = {
    symbol,
    side: values.side,
    qty: quantityResult.quantity,
    order_type: values.orderType,
    outside_rth: values.outsideRth,
  };

  if (values.orderType === 'LMT') {
    const limitPrice = positiveNumber(values.limitPrice);
    if (limitPrice == null) return { ok: false, error: 'Limit price is required' };
    payload.limit_price = limitPrice;
  }
  if (values.orderType === 'STP') {
    const stopPrice = positiveNumber(values.stopPrice);
    if (stopPrice == null) return { ok: false, error: 'Stop price is required' };
    payload.stop_price = stopPrice;
  }

  return {
    ok: true,
    payload,
    quantity: quantityResult.quantity,
    referencePrice: quantityResult.referencePrice,
  };
}
