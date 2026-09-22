/**
 * The honesty marker: every practice fill is an estimate. Rendered beside a
 * practice fill in the ticket's `Last:` line, the drawer footer and the quote
 * card's venue tag -- never beside a broker execution.
 */
import { TRADER_EST_CHIP, TRADER_EST_CHIP_TITLE } from '../constantGroups/trader_chrome';

export function EstChip() {
  return (
    <b className="sv-est" title={TRADER_EST_CHIP_TITLE} data-testid="est-chip">
      {TRADER_EST_CHIP}
    </b>
  );
}
