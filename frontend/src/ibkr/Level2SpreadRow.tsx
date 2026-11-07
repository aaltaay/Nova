/**
 * The spread row over the book (operator asks, 2026-11-06; mockup v1, then "the bid and ask next to each
 * other"): one line, the best bid, the spread with its share of the ask, and the best ask side by side in the
 * middle. It used to be one muted line under the book; on top, every number the trade needs is in one glance.
 * The band over the tape (TapeLastBand) is the same height, so both panes start on one line.
 */
import { L2_SPREAD_LABELS } from '../constants';
import { formatDepthPrice } from './depthNumberFormat';

interface Props {
  bid: number | null | undefined;
  ask: number | null | undefined;
}

/** The spread as a share of the ask, two decimals; null without a positive ask. */
export function spreadPercent(bid: number, ask: number): string | null {
  if (!(ask > 0)) return null;
  return `${((Math.abs(ask - bid) / ask) * 100).toFixed(2)}%`;
}

export function Level2SpreadRow({ bid, ask }: Props) {
  if (bid == null || ask == null) return null;
  const spread = Math.abs(ask - bid);
  const pct = spreadPercent(bid, ask);
  return (
    <div className="l2-band das-l2-spread" data-testid="l2-spread">
      <div className="l2-band__inner">
      <div className="das-l2-spread__side das-l2-spread__side--bid">
        <span className="l2-band__label">{L2_SPREAD_LABELS.bid}</span>
        <span className="l2-band__num" data-testid="l2-spread-bid">{formatDepthPrice(bid)}</span>
      </div>
      <div className="das-l2-spread__mid">
        <span className="l2-band__label">{L2_SPREAD_LABELS.spread}</span>
        <span className="l2-band__num" data-testid="l2-spread-value">{formatDepthPrice(spread)}</span>
        {pct && <span className="das-l2-spread__pct" data-testid="l2-spread-pct">{pct}</span>}
      </div>
      <div className="das-l2-spread__side das-l2-spread__side--ask">
        <span className="l2-band__label">{L2_SPREAD_LABELS.ask}</span>
        <span className="l2-band__num" data-testid="l2-spread-ask">{formatDepthPrice(ask)}</span>
      </div>
      </div>
    </div>
  );
}
