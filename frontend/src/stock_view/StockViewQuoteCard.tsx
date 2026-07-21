/** Dense quote stats for Stock View rail — wrapped in shared module card. */
import { CompactGridCell } from '../components/CompactGridCell';
import {
  QUOTE_RVOL_DAILY_LABEL,
  QUOTE_RVOL_DAILY_TITLE,
  REL_VOLUME_HIGH,
  STOCK_VIEW_MODULE_QUOTE_TITLE,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import {
  fmtPct,
  fmtSessionPrice,
  fmtVolume,
} from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { StockViewModuleCard } from './StockViewModuleCard';

interface Props {
  detail: TickerDetail;
  /** When true, omit duplicate symbol/price (page header already shows them). */
  hidePrice?: boolean;
}

export function StockViewQuoteCard({ detail, hidePrice = true }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);
  const daily = detail.snapshot?.daily_bar;

  return (
    <StockViewModuleCard
      title={STOCK_VIEW_MODULE_QUOTE_TITLE}
      className="sv-quote-card"
      testId="stock-view-quote-card"
      aria-label="Stock Quote"
    >
      <div data-module="stock-view-quote">
        {!hidePrice && (
          <div className="sv-quote-card__price">
            <span className="sv-quote-card__symbol">{detail.symbol}</span>
            {m.mainPrice != null && (
              <span className="sv-quote-card__last">{m.mainPrice.toFixed(2)}</span>
            )}
            {m.mainChangeAbs != null && (
              <span
                className={`sv-quote-card__chg ${(m.mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
              >
                {m.mainChangeAbs >= 0 ? '+' : ''}
                {m.mainChangeAbs.toFixed(2)} ({fmtPct(m.mainChangePct)})
              </span>
            )}
          </div>
        )}
        <div className="sv-quote-card__grid compact-grid">
          <CompactGridCell label="Float" value={fmtVolume(detail.fundamentals?.float_shares)} />
          <CompactGridCell label="Vol" value={fmtVolume(daily?.volume)} />
          <CompactGridCell
            label={QUOTE_RVOL_DAILY_LABEL}
            value={detail.rel_volume != null ? detail.rel_volume.toFixed(2) : '—'}
            valueClass={
              detail.rel_volume != null && detail.rel_volume >= REL_VOLUME_HIGH
                ? 'positive'
                : undefined
            }
            title={QUOTE_RVOL_DAILY_TITLE}
          />
          <CompactGridCell
            label="Gap%"
            value={m.gapPct != null ? `${(m.gapPct * 100).toFixed(2)}` : '—'}
            valueClass={
              m.gapPct != null ? (m.gapPct >= 0 ? 'positive' : 'negative') : undefined
            }
          />
          <CompactGridCell label="High" value={fmtSessionPrice(daily?.high)} />
          <CompactGridCell label="Low" value={fmtSessionPrice(daily?.low)} />
        </div>
      </div>
    </StockViewModuleCard>
  );
}
