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
 *
 * A request nobody hears is dropped, so the channel also keeps one fact: which
 * symbols have a mounted ticket listening in this window (#566). A sender that
 * cannot queue -- the chart menu -- reads `orderTicketListening` and locks its
 * rows with a reason instead of staging into nothing.
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

/** Mounted tickets listening per symbol (a count: two Trader tabs may share one). */
const listening = new Map<string, number>();
const listeningWatchers = new Set<() => void>();

function countListening(key: string, delta: 1 | -1): void {
  if (!key) return;
  const next = (listening.get(key) ?? 0) + delta;
  if (next > 0) listening.set(key, next);
  else listening.delete(key);
  for (const watcher of [...listeningWatchers]) watcher();
}

/** True while a mounted ticket in this window takes prefills for `symbol`. */
export function orderTicketListening(symbol: string): boolean {
  return listening.has(symbol.trim().toUpperCase());
}

/** Called whenever a ticket starts or stops listening (`useSyncExternalStore`). */
export function watchOrderTicketListening(onChange: () => void): () => void {
  listeningWatchers.add(onChange);
  return () => {
    listeningWatchers.delete(onChange);
  };
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
  countListening(key, 1);
  let subscribed = true;
  return () => {
    window.removeEventListener(ORDER_TICKET_PREFILL_EVENT, onEvent);
    if (!subscribed) return;
    subscribed = false;
    countListening(key, -1);
  };
}
