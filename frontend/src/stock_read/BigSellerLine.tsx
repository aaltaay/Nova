/**
 * The held card's line about big sellers on the ask -- big buyers on the bid, for a short (#846): the call,
 * "taken" or "pulled" when it ends, that none is there, or why there is no read (no depth line, a stale one,
 * nothing recorded on a replay). Shown, never acted on: it places, moves and gates nothing.
 */
import { tipProps } from '../ux';
import { bigLine } from './bigSeller';
import type { StockReadContextValue } from './StockReadContext';
import './bigSeller.css';

export function BigSellerLine({ big, short }: { big: StockReadContextValue['big']; short: boolean }) {
  if (!big || big.unavailable) return null;   // an API from before the read, or the sample desk
  const line = bigLine(big.data, short, big.error);
  return (
    <p className={`sr-big sr-big--${line.tone}`} data-testid="held-big" role="status"
      {...tipProps(line.detail || null, short ? 'Big buyer on the bid' : 'Big seller on the ask')}>
      <span className="sr-big__k">L2</span>
      <span className="sr-big__t">{line.text}</span>
    </p>
  );
}
