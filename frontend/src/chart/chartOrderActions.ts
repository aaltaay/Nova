/**
 * The chart's only money seam. Maps a menu row to an order-ticket prefill --
 * it never calls `placeIbkrOrder`, never re-implements a gate, and never
 * flattens (Close Position stays on `ClosePositionButton` -> `closeFullPosition`).
 */
import { defaultTicketQty, getConfirmedDeskVenueSnapshot } from '../ibkr';
import type { ManualOrderSide } from '../ibkr/orderEntry';
import {
  requestOrderTicketPrefill,
  type OrderTicketPrefill,
} from '../ibkr/orderTicketPrefill';
import { formatSeedPrice } from '../ibkr/tradeDefaultSeed';

export type ChartOrderIntent = 'create_order' | 'buy' | 'sell' | 'short';

export function chartOrderSide(intent: ChartOrderIntent): ManualOrderSide {
  return intent === 'sell' || intent === 'short' ? 'SELL' : 'BUY';
}

/** Pure: what the ticket will receive for this click. */
export function chartOrderPrefill(input: {
  symbol: string;
  intent: ChartOrderIntent;
  price: number;
  quantityValue?: string;
}): OrderTicketPrefill {
  return {
    symbol: input.symbol.trim().toUpperCase(),
    side: chartOrderSide(input.intent),
    orderType: 'LMT',
    quantityValue: input.quantityValue ?? defaultTicketQty(getConfirmedDeskVenueSnapshot().venue),
    limitPrice: formatSeedPrice(input.price),
    // ADR 048: a short lands on the ticket's Short side, which starts its buy stop at the venue's offset.
    ...(input.intent === 'short' ? { shortEntry: true } : {}),
  };
}

export function stageChartOrder(input: {
  symbol: string;
  intent: ChartOrderIntent;
  price: number;
}): OrderTicketPrefill {
  const prefill = chartOrderPrefill(input);
  requestOrderTicketPrefill(prefill);
  return prefill;
}
