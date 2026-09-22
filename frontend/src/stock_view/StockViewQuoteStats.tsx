/** Compact Float / Vol / RVOL / Gap / High / Low row for the Stock Quote card. */
import { CompactGridCell } from '../components/CompactGridCell';
import {
  QUOTE_RVOL_DAILY_LABEL,
  QUOTE_RVOL_DAILY_TITLE,
  REL_VOLUME_HIGH,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import { fmtSessionPrice, fmtVolume, pctToneClass } from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { QUOTE_GAP_OPEN_TITLE } from '../constantGroups/trader_view';

interface Props {
  detail: TickerDetail;
}

export function StockViewQuoteStats({ detail }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);
  const daily = detail.snapshot?.daily_bar;

  return (
    <div
      className="sv-quote-card__grid compact-grid sv-quote-stats"
      data-module="stock-view-quote"
      data-testid="stock-view-quote-stats"
    >
      <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
      <CompactGridCell label="Vol" value={fmtVolume(daily?.volume)} />
      <CompactGridCell
        label={QUOTE_RVOL_DAILY_LABEL}
        value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '--'}
        valueClass={
          detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH
            ? 'positive'
            : undefined
        }
        title={QUOTE_RVOL_DAILY_TITLE}
      />
      <CompactGridCell
        label="Gap%"
        value={m.gapPct != null ? `${(m.gapPct * 100).toFixed(2)}` : '--'}
        valueClass={pctToneClass(m.gapPct) || undefined}
        title={QUOTE_GAP_OPEN_TITLE}
      />
      <CompactGridCell label="High" value={fmtSessionPrice(daily?.high)} />
      <CompactGridCell label="Low" value={fmtSessionPrice(daily?.low)} />
    </div>
  );
}
