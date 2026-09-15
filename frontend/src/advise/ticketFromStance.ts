import { defaultTicketQty } from '../ibkr/applyTicketDefaults';
import {
  requestOrderTicketPrefill,
  type OrderTicketPrefill,
} from '../ibkr/orderTicketPrefill';
import type { AdviseResult, AdviseTicketPrefill } from './types';

export function adviseTicketPrefill(
  symbol: string,
  result: AdviseResult | null | undefined,
): OrderTicketPrefill | null {
  const ticket = result?.ticket;
  if (!ticket || ticket.places) return null;
  const side = ticket.side === 'SELL' ? 'SELL' : 'BUY';
  return {
    symbol: symbol.trim().toUpperCase(),
    side,
    orderType: ticket.order_type === 'LMT' ? 'LMT' : ticket.order_type === 'STP' ? 'STP' : 'MKT',
    quantityValue: ticket.quantity_value || defaultTicketQty(),
    limitPrice: ticket.limit_price || '',
  };
}

/** Stage the ticket only. Never calls place. */
export function stageAdviseTicket(ticket: AdviseTicketPrefill): OrderTicketPrefill | null {
  const parsed = adviseTicketPrefill(ticket.symbol, { stance: null, reasons: [], risks: [], ticket });
  if (!parsed) return null;
  requestOrderTicketPrefill(parsed);
  return parsed;
}
