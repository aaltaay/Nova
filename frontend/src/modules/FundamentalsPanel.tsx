/** Key stats + fundamentals grid + broker listing attributes. */
import { CompactGridCell } from '../components/CompactGridCell';
import { TickerBrokerGrid } from '../components/TickerBrokerGrid';
import {
  QUOTE_AVG_VOLUME_LABEL,
  QUOTE_RVOL_DAILY_LABEL,
  QUOTE_RVOL_DAILY_TITLE,
  REL_VOLUME_HIGH,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import {
  fmtMarketCap,
  fmtPrice,
  fmtSessionPrice,
  fmtVolume,
} from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from './quoteMetrics';

interface Props {
  detail: TickerDetail;
  /**
   * `key` — compact key-stats grid (columns quote col).
   * `full` — key stats + fundamentals + broker (stack layout).
   * `fundamentals` — fundamentals + broker only (columns fund col).
   */
  variant?: 'key' | 'full' | 'fundamentals';
  showTitle?: boolean;
}

export function FundamentalsPanel({
  detail,
  variant = 'full',
  showTitle = false,
}: Props) {
  const { discoveryProvider } = useWorkspace();
  const { gapPct, prevClose } = computeQuoteMetrics(detail, discoveryProvider);
  const daily = detail.snapshot?.daily_bar;
  const asset = detail.asset;
  const includeKey = variant === 'key' || variant === 'full';
  const includeFund = variant === 'full' || variant === 'fundamentals';
  const includeBroker = includeFund;

  const keyCells = (
    <>
      <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
      <CompactGridCell label="Volume" value={fmtVolume(daily?.volume)} />
      <CompactGridCell label={QUOTE_AVG_VOLUME_LABEL} value={fmtVolume(detail.avg_volume ?? null)} />
      <CompactGridCell
        label={QUOTE_RVOL_DAILY_LABEL}
        value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
        valueClass={
          detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH ? 'positive' : undefined
        }
        title={QUOTE_RVOL_DAILY_TITLE}
      />
      {variant === 'full' && (
        <>
          <CompactGridCell
            label="Relative Volume (5 min)"
            value={detail.rvol_5min != null ? `${detail.rvol_5min.toFixed(2)}x` : '—'}
            valueClass={
              detail.rvol_5min != null && detail.rvol_5min >= REL_VOLUME_HIGH
                ? 'positive'
                : undefined
            }
          />
          <CompactGridCell
            label="Volume In 5 Minutes"
            value={detail.volume_in_5min != null ? fmtVolume(detail.volume_in_5min) : '—'}
          />
        </>
      )}
      <CompactGridCell
        label="Gap(%)"
        value={gapPct != null ? `${(gapPct * 100).toFixed(2)}` : '—'}
        valueClass={gapPct != null ? (gapPct >= 0 ? 'positive' : 'negative') : undefined}
      />
      <CompactGridCell label="Open" value={fmtSessionPrice(daily?.open)} />
      <CompactGridCell label="Previous Close" value={fmtPrice(prevClose)} />
      <CompactGridCell label="High Price" value={fmtSessionPrice(daily?.high)} />
      <CompactGridCell label="Low Price" value={fmtSessionPrice(daily?.low)} />
    </>
  );

  const fundCells = (
    <>
      <CompactGridCell
        label="High In 52 Weeks"
        value={fmtPrice(detail.fundamentals?.fifty_two_week_high)}
      />
      <CompactGridCell
        label="Low In 52 Weeks"
        value={fmtPrice(detail.fundamentals?.fifty_two_week_low)}
      />
      <CompactGridCell
        label="Short Interest"
        value={fmtVolume(detail.fundamentals?.short_interest)}
      />
      <CompactGridCell
        label="Earnings Date"
        value={detail.fundamentals?.earnings_date ?? '—'}
      />
      <CompactGridCell
        label="Market Cap"
        value={fmtMarketCap(detail.fundamentals?.market_cap)}
      />
      <CompactGridCell label="Industry" value={detail.fundamentals?.industry ?? '—'} />
      <CompactGridCell label="Sector" value={detail.fundamentals?.sector ?? '—'} />
      <CompactGridCell label="Recent Split" value={detail.fundamentals?.recent_split ?? '—'} />
      <CompactGridCell label="Exchange Group" value={asset?.exchange ?? '—'} />
    </>
  );

  return (
    <div
      className="nova-module nova-module--fundamentals"
      data-module="fundamentals"
      data-variant={variant}
    >
      {showTitle && <div className="cq-section-title">Fundamentals</div>}
      {variant === 'key' ? (
        <div className="cq-grid cq-grid-key">{keyCells}</div>
      ) : (
        <div className="cq-grid">
          {includeKey && keyCells}
          {includeFund && fundCells}
        </div>
      )}
      {includeBroker && <TickerBrokerGrid asset={asset} listing={detail.listing} />}
    </div>
  );
}
