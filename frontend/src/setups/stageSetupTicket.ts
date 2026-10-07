/** "Stage ticket": open the symbol's Trader tab and fill its manual ticket with
 * a BUY limit at the setup's entry -- a short setup's (ADR 049) a short limit with
 * its buy stop on the ticket's Short side, never a buy. It never places -- a human
 * presses Place, with every ticket gate (arming, PIN, confirm, quantity cap, the
 * short check) in force.
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
import { fmtPx } from './setupsFormat';
import { isShortRow } from './shortWords';

/** Draw the venue guard before Stage is pressed, including the sample desk. */
export function stageVenueLock(venue: DeskVenue | null, sample = false): string | null {
  if (sample || isSampleView()) return SAMPLE_WRITE_REFUSAL;
  return venue === null ? TRADE_DEFAULTS_WAITING : null;
}

/** A short proposal's Stage (ADR 049): the buy stop it goes in with; null for a long. A short with no stop
 * stages nothing (`buyStop` empty): no stop, no short. */
export function shortStageOf(p: { side?: string | null; setup_type?: string | null; stop: number | null }):
  { buyStop: string } | null {
  if (!isShortRow(p)) return null;
  return { buyStop: p.stop != null && Number.isFinite(p.stop) && p.stop > 0 ? fmtPx(p.stop) : '' };
}

export function stageSetupTicket(
  symbol: string,
  limitPrice: string,
  openTrader: (symbol: string) => void,
  quantity?: number | null,
  short: { buyStop: string } | null = null,
): boolean {
  const asked = getConfirmedDeskVenueSnapshot();
  if (!asked.venue || !asked.generation || !isConfirmedDeskVenueSnapshotCurrent(asked)) return false;
  if (!symbol || !limitPrice) return false;
  if (short && !short.buyStop) return false;
  if (quantity !== undefined && (quantity === null || !(quantity >= 1))) return false;
  openTrader(symbol);
  const req = {
    symbol,
    side: (short ? 'SELL' : 'BUY') as 'SELL' | 'BUY',
    orderType: 'LMT' as const,
    quantityValue: quantity === undefined ? defaultTicketQty(asked.venue) : String(Math.floor(quantity)),
    limitPrice,
    ...(short ? { shortEntry: true, buyStop: short.buyStop } : {}),
  };
  // The Trader tab's ticket may still be mounting: stage now and once more after it has.
  requestOrderTicketPrefill(req);
  window.setTimeout(() => {
    if (isConfirmedDeskVenueSnapshotCurrent(asked)) requestOrderTicketPrefill(req);
  }, SETUPS_STAGE_TICKET_DELAY_MS);
  return true;
}
