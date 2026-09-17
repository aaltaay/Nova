/**
 * Ticket Side: Buy / Sell / Short. Short only when account_class is Margin.
 * Sell never opens a short -- that is Short + short_entry.
 */
import {
  TICKER_TRADE_LABEL_BUY,
  TICKER_TRADE_LABEL_SELL,
  TICKER_TRADE_LABEL_SHORT,
} from '../constantGroups/shortability';
import { shortSideVisible } from './accountType';
import type { ManualOrderSide } from './orderEntry';
import type { IbkrAccountSummary } from './types';

export type TicketSide = 'buy' | 'sell' | 'short';

const MARGIN_SIDES: readonly TicketSide[] = ['buy', 'sell', 'short'];
const CASH_SIDES: readonly TicketSide[] = ['buy', 'sell'];

export function ticketSideOptions(kind: 'cash' | 'margin' | 'unknown'): readonly TicketSide[] {
  return kind === 'margin' ? MARGIN_SIDES : CASH_SIDES;
}

export function allowShortSide(summary: IbkrAccountSummary | null | undefined): boolean {
  return shortSideVisible(summary ?? null);
}

export function ticketSideToOrder(side: TicketSide): {
  side: ManualOrderSide;
  shortEntry: boolean;
} {
  if (side === 'buy') return { side: 'BUY', shortEntry: false };
  if (side === 'short') return { side: 'SELL', shortEntry: true };
  return { side: 'SELL', shortEntry: false };
}

export function orderSideToTicketSide(side: ManualOrderSide): TicketSide {
  return side === 'SELL' ? 'sell' : 'buy';
}

export function placeActionLabel(side: TicketSide, symbol: string): string {
  const verb =
    side === 'buy'
      ? TICKER_TRADE_LABEL_BUY
      : side === 'short'
        ? TICKER_TRADE_LABEL_SHORT
        : TICKER_TRADE_LABEL_SELL;
  const sym = symbol.trim().toUpperCase();
  return sym ? `${verb} ${sym}` : verb;
}

export function clampTicketSide(
  side: TicketSide,
  allowShort: boolean,
): TicketSide {
  if (side === 'short' && !allowShort) return 'sell';
  return side;
}
