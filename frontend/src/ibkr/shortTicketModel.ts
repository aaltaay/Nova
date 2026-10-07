/**
 * The ticket follows your position (ADR 048, #778 step 3). Pure.
 *
 * - Flat: Buy / Short. Sell is off: selling shares you do not own is a short, which goes out with its stop.
 * - Long: Buy / Sell, with Short off ("you're long; Nova never flips").
 * - Short: Cover / Short more, with Sell off (a sell would add to the short without its buy stop).
 *
 * A short opens with a Limit and a required Buy stop over it. Under SSR -- on, or not known, which counts
 * as on -- its limit starts at the ask: a short under SSR may execute only above the bid. A cover is a BUY,
 * never past flat; the door and the practice broker hold that line, and the ticket says it.
 */
import {
  SHORT_LIMIT_NOTE_SSR,
  SHORT_LIMIT_NOTE_SSR_UNKNOWN,
  SHORT_NOTE_COVER,
  SHORT_NOTE_MORE,
  SHORT_NOTE_OPEN,
  SHORT_STOP_WHY_MISSING,
  SHORT_STOP_WHY_UNDER,
  SHORT_TICKET_LABEL_COVER,
  SHORT_TICKET_LABEL_SHORT_MORE,
  SHORT_WHY_FLAT_SELL,
  SHORT_WHY_LONG,
  SHORT_WHY_SHORT_SELL,
} from '../constantGroups/short_ticket';
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import type { TicketSide } from './ticketSide';

export type HeldSide = 'flat' | 'long' | 'short';

export function heldSide(qty: number | null | undefined): HeldSide {
  if (qty == null || !Number.isFinite(qty) || qty === 0) return 'flat';
  return qty > 0 ? 'long' : 'short';
}

export interface SideButton {
  side: TicketSide;
  label: string;
  /** Why it cannot be pressed now (null: it can). */
  lock: string | null;
  /** The colour it wears when pressed: a cover is a buy back, green; a short orange. */
  tone: 'buy' | 'sell' | 'short' | 'cover';
}

/** The three side buttons for the position held. ``known`` false: the position is not read yet, and the
 * ticket locks nothing on a guess (the door still refuses a sale past what you hold). */
export function sideButtons(args: {
  symbol: string;
  qty: number | null | undefined;
  known: boolean;
  allowShort: boolean;
  shortBlock: string | null;
}): SideButton[] {
  const sym = args.symbol.trim().toUpperCase();
  const held = args.known ? heldSide(args.qty) : 'flat';
  const buy: SideButton = held === 'short'
    ? { side: 'buy', label: SHORT_TICKET_LABEL_COVER, lock: null, tone: 'cover' }
    : { side: 'buy', label: TICKER_TRADE_LABEL_BUY, lock: null, tone: 'buy' };
  let sellLock: string | null = null;
  if (args.known && held === 'flat') sellLock = SHORT_WHY_FLAT_SELL(sym);
  if (args.known && held === 'short') sellLock = SHORT_WHY_SHORT_SELL(sym);
  const sell: SideButton = { side: 'sell', label: TICKER_TRADE_LABEL_SELL, lock: sellLock, tone: 'sell' };
  if (!args.allowShort) return [buy, sell];
  const shortLock = args.known && held === 'long' ? SHORT_WHY_LONG(sym) : args.shortBlock;
  const short: SideButton = {
    side: 'short',
    label: held === 'short' ? SHORT_TICKET_LABEL_SHORT_MORE : TICKER_TRADE_LABEL_SHORT,
    lock: shortLock,
    tone: 'short',
  };
  return [buy, sell, short];
}

/** The button with this side, open (no lock), or null. */
export function openSide(buttons: SideButton[], side: TicketSide): SideButton | null {
  return buttons.find((b) => b.side === side && !b.lock) ?? null;
}

/**
 * The side the ticket moves to when the pressed one locks (the position changed under it): Short gives way to
 * Sell when you went long, anything else to Buy -- which is Cover while you are short. Buy never locks.
 */
export function sideAfterLock(side: TicketSide, buttons: SideButton[]): TicketSide {
  if (openSide(buttons, side)) return side;
  if (side === 'short' && openSide(buttons, 'sell')) return 'sell';
  return 'buy';
}

function sharesWords(n: number): string {
  return Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: 4 }) : '?';
}

/** The line under the sides that says what this order does to the position (null: nothing to add). */
export function sideNote(ticketSide: TicketSide, qty: number | null | undefined, orderQty: string, symbol: string): string | null {
  const sym = symbol.trim().toUpperCase();
  const held = heldSide(qty);
  if (ticketSide === 'short') {
    return held === 'short'
      ? SHORT_NOTE_MORE(sharesWords(Math.abs(qty as number)), sym)
      : SHORT_NOTE_OPEN(orderQty.trim() || '?', sym);
  }
  if (ticketSide === 'buy' && held === 'short') return SHORT_NOTE_COVER(sharesWords(Math.abs(qty as number)));
  return null;
}

function px(raw: string | number | null | undefined): string | null {
  const n = typeof raw === 'number' ? raw : Number(String(raw ?? '').trim());
  return raw === '' || raw == null || !Number.isFinite(n) || n <= 0 ? null : n.toFixed(2);
}

/**
 * The submit button's words. A short says its size, price and stop ("Short RDYN · 416 @ 5.77 · stop 5.89"),
 * a cover its size and price ("Cover RDYN · 416 @ 5.46"); anything else is null (the ticket's own label).
 */
export function shortSubmitLabel(args: {
  ticketSide: TicketSide;
  qty: number | null | undefined;
  symbol: string;
  orderQty: string;
  limit: string;
  buyStop: string;
  orderType: string;
}): string | null {
  const sym = args.symbol.trim().toUpperCase();
  const held = heldSide(args.qty);
  const shares = args.orderQty.trim();
  const limit = args.orderType === 'MKT' ? null : px(args.limit);
  if (args.ticketSide === 'short') {
    const verb = held === 'short' ? SHORT_TICKET_LABEL_SHORT_MORE : TICKER_TRADE_LABEL_SHORT;
    const stop = px(args.buyStop);
    const bits = [`${verb} ${sym}`, shares ? `${shares}${limit ? ` @ ${limit}` : ''}` : null, stop ? `stop ${stop}` : null];
    return bits.filter(Boolean).join(' · ');
  }
  if (args.ticketSide === 'buy' && held === 'short') {
    return [`${SHORT_TICKET_LABEL_COVER} ${sym}`, shares ? `${shares}${limit ? ` @ ${limit}` : ''}` : null]
      .filter(Boolean).join(' · ');
  }
  return null;
}

/** Why the short cannot be sent as typed (its buy stop), or null. */
export function buyStopRefusal(limit: string, buyStop: string): string | null {
  const stop = px(buyStop);
  if (stop === null) return SHORT_STOP_WHY_MISSING;
  const lim = px(limit);
  if (lim !== null && Number(stop) <= Number(lim)) return SHORT_STOP_WHY_UNDER(lim);
  return null;
}

/** The buy stop a short starts with: ``offset`` dollars over the limit. */
export function seedBuyStop(limit: string | number | null | undefined, offset: number): string {
  const lim = px(limit);
  if (lim === null || !(offset > 0)) return '';
  return (Number(lim) + offset).toFixed(2);
}

/** Where a short's limit starts: the ask while SSR is on or not known (above the bid, as SSR requires), else the bid. */
export function shortLimitSide(ssrEffective: boolean | null | undefined): 'ask' | 'bid' {
  return ssrEffective === false ? 'bid' : 'ask';
}

/** The note under a short's limit: why it sits at the ask (SSR on, or not known yet), or null when SSR is off. */
export function shortLimitNote(ssrEffective: boolean | null | undefined): string | null {
  if (ssrEffective === false) return null;
  return ssrEffective === true ? SHORT_LIMIT_NOTE_SSR : SHORT_LIMIT_NOTE_SSR_UNKNOWN;
}

/** What the short loses at its buy stop: (stop - limit) x shares, or null when any is unknown. */
export function riskAtStop(limit: string, buyStop: string, orderQty: string): number | null {
  const lim = px(limit);
  const stop = px(buyStop);
  const n = Number(orderQty);
  if (lim === null || stop === null || !Number.isFinite(n) || n <= 0) return null;
  return Math.round((Number(stop) - Number(lim)) * n * 100) / 100;
}
