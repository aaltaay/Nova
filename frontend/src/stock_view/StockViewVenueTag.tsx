/**
 * The quote card's venue tag: `PAPER · fills est`, `SIM · live edge · fills
 * est`, `SIM · replay · fills est`. It replaces the full-width Paper banner
 * on the Trader view (operator decision, 2026-09-21): the practice venue is
 * a fact about the card, not a band over the page. Live and disconnected
 * show nothing -- a real venue needs no `est` marker.
 */
import {
  TRADER_VENUE_TAG_FILLS,
  TRADER_VENUE_TAG_LIVE_EDGE,
  TRADER_VENUE_TAG_PAPER,
  TRADER_VENUE_TAG_PAPER_TITLE,
  TRADER_VENUE_TAG_REPLAY,
  TRADER_VENUE_TAG_SIM,
  TRADER_VENUE_TAG_SIM_TITLE,
} from '../constantGroups/trader_chrome';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useSimReplayTarget } from '../sim/useSimReplayTarget';
import { EstChip } from './EstChip';

export { EstChip } from './EstChip';

export function StockViewVenueTag({ symbol }: { symbol: string }) {
  const mode = useIbkrStatus().mode;
  const { clock } = useSimReplayTarget(symbol);
  if (mode !== 'paper' && mode !== 'sim') return null;
  const sim = mode === 'sim';
  const state = sim ? (clock?.live_edge ? TRADER_VENUE_TAG_LIVE_EDGE : TRADER_VENUE_TAG_REPLAY) : null;
  return (
    <span
      className={`sv-venue-tag sv-venue-tag--${mode}`}
      data-testid="stock-view-venue-tag"
      title={sim ? TRADER_VENUE_TAG_SIM_TITLE : TRADER_VENUE_TAG_PAPER_TITLE}
    >
      <span className="sv-venue-tag__venue">{sim ? TRADER_VENUE_TAG_SIM : TRADER_VENUE_TAG_PAPER}</span>
      {state && <span className="sv-venue-tag__state">· {state}</span>}
      <span className="sv-venue-tag__fills">· {TRADER_VENUE_TAG_FILLS} <EstChip /></span>
    </span>
  );
}
