/**
 * One-way request channel: "stage this order on the manual ticket".
 *
 * Money SSOT (ADR 007): chart menus never build or send an order themselves.
 * They stage side / qty / limit price on the already-mounted ManualOrderTicket,
 * so the padlock, spend lock, the confirm dialog and paper/live all stay in
 * `useManualOrderSubmission` -> `placeIbkrOrder`. `auto_live` is unaffected --
 * a human still presses Place.
 *
 * Same latch-free CustomEvent shape as `stock_view/requestDockSurface.ts`.
 */
import type { ManualOrderSide, ManualOrderType } from './orderEntry';

export const ORDER_TICKET_PREFILL_EVENT = 'nova:order-ticket-prefill';

export interface OrderTicketPrefill {
  symbol: string;
  side: ManualOrderSide;
  orderType: ManualOrderType;
  /** Share count, already formatted the way the ticket input holds it. */
  quantityValue: string;
  /** Formatted limit price; empty for non-limit orders. */
  limitPrice: string;
}

function isSide(value: unknown): value is ManualOrderSide {
  return value === 'BUY' || value === 'SELL';
}

function isOrderType(value: unknown): value is ManualOrderType {
  return value === 'MKT' || value === 'LMT' || value === 'STP';
}

export function parseOrderTicketPrefill(detail: unknown): OrderTicketPrefill | null {
  if (!detail || typeof detail !== 'object') return null;
  const req = detail as Partial<OrderTicketPrefill>;
  const symbol = typeof req.symbol === 'string' ? req.symbol.trim().toUpperCase() : '';
  if (!symbol) return null;
  if (!isSide(req.side) || !isOrderType(req.orderType)) return null;
  if (typeof req.quantityValue !== 'string' || !req.quantityValue) return null;
  const limitPrice = typeof req.limitPrice === 'string' ? req.limitPrice : '';
  if (req.orderType === 'LMT' && !limitPrice) return null;
  return {
    symbol,
    side: req.side,
    orderType: req.orderType,
    quantityValue: req.quantityValue,
    limitPrice,
  };
}

export function requestOrderTicketPrefill(req: OrderTicketPrefill): void {
  const parsed = parseOrderTicketPrefill(req);
  if (!parsed) return;
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(ORDER_TICKET_PREFILL_EVENT, { detail: parsed }),
  );
}

/** Subscribe the ticket that owns `symbol`; requests for other symbols are ignored. */
export function subscribeOrderTicketPrefill(
  symbol: string,
  handler: (req: OrderTicketPrefill) => void,
): () => void {
  if (typeof window === 'undefined') return () => {};
  const key = symbol.trim().toUpperCase();
  const onEvent = (event: Event) => {
    const parsed = parseOrderTicketPrefill((event as CustomEvent).detail);
    if (!parsed || parsed.symbol !== key) return;
    handler(parsed);
  };
  window.addEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent);
  return () => window.removeEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent);
}
