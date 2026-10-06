/** "Stage ticket": open the symbol's Trader tab and fill its manual ticket with
 * a BUY limit at the setup's entry. It never places -- a human presses Place,
 * with every ticket gate (arming, PIN, confirm, quantity cap) in force.
 *
 * The size is the caller's: the venue sleeve's risk per trade over the setup's
 * risk a share (`proposalStageSize`, ADR 042 draft). A caller that passes none
 * gets Settings > Trade's default quantity -- only a caller not yet moved to
 * risk sizing (the Bots page inbox) does. */
import { SETUPS_STAGE_TICKET_DELAY_MS } from '../constants';
import { defaultTicketQty, getConfirmedDeskVenueSnapshot, isConfirmedDeskVenueSnapshotCurrent } from '../ibkr';
import { requestOrderTicketPrefill } from '../ibkr/orderTicketPrefill';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { TRADE_DEFAULTS_WAITING } from '../constantGroups/trade_defaults';
import { isSampleView } from '../sample_data/sampleNav';
import { SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';

/** Draw the venue guard before Stage is pressed, including the sample desk. */
export function stageVenueLock(venue: DeskVenue | null, sample = false): string | null {
  if (sample || isSampleView()) return SAMPLE_WRITE_REFUSAL;
  return venue === null ? TRADE_DEFAULTS_WAITING : null;
}

export function stageSetupTicket(
  symbol: string,
  limitPrice: string,
  openTrader: (symbol: string) => void,
  quantity?: number | null,
): boolean {
  const asked = getConfirmedDeskVenueSnapshot();
  if (!asked.venue || !asked.generation || !isConfirmedDeskVenueSnapshotCurrent(asked)) return false;
  if (!symbol || !limitPrice) return false;
  if (quantity !== undefined && (quantity === null || !(quantity >= 1))) return false;
  openTrader(symbol);
  const req = {
    symbol,
    side: 'BUY' as const,
    orderType: 'LMT' as const,
    quantityValue: quantity === undefined ? defaultTicketQty(asked.venue) : String(Math.floor(quantity)),
    limitPrice,
  };
  // The Trader tab's ticket may still be mounting: stage now and once more after it has.
  requestOrderTicketPrefill(req);
  window.setTimeout(() => {
    if (isConfirmedDeskVenueSnapshotCurrent(asked)) requestOrderTicketPrefill(req);
  }, SETUPS_STAGE_TICKET_DELAY_MS);
  return true;
}
