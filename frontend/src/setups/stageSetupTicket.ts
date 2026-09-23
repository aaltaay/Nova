/** "Stage ticket": open the symbol's Trader tab and fill its manual ticket with
 * a BUY limit at the setup's entry. It never places -- a human presses Place,
 * with every ticket gate (arming, PIN, confirm, quantity cap) in force. */
import { SETUPS_STAGE_TICKET_DELAY_MS } from '../constants';
import { defaultTicketQty } from '../ibkr/applyTicketDefaults';
import { requestOrderTicketPrefill } from '../ibkr/orderTicketPrefill';

export function stageSetupTicket(
  symbol: string,
  limitPrice: string,
  openTrader: (symbol: string) => void,
): boolean {
  if (!symbol || !limitPrice) return false;
  openTrader(symbol);
  const req = {
    symbol,
    side: 'BUY' as const,
    orderType: 'LMT' as const,
    quantityValue: defaultTicketQty(),
    limitPrice,
  };
  // The Trader tab's ticket may still be mounting: stage now and once more after it has.
  requestOrderTicketPrefill(req);
  window.setTimeout(() => requestOrderTicketPrefill(req), SETUPS_STAGE_TICKET_DELAY_MS);
  return true;
}
