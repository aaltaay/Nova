/** Dense quote stats for Stock View — wrapped in shared module card (standalone uses). */
import {
  STOCK_VIEW_MODULE_QUOTE_TITLE,
} from '../constants';
import type { TickerDetail } from '../types/ticker';
import { fmtPct } from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { StockViewModuleCard } from './StockViewModuleCard';
import { StockViewQuoteStats } from './StockViewQuoteStats';

interface Props {
  detail: TickerDetail;
  /** When true, omit duplicate symbol/price (page header already shows them). */
  hidePrice?: boolean;
}

export function StockViewQuoteCard({ detail, hidePrice = true }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);

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
        <StockViewQuoteStats detail={detail} />
      </div>
    </StockViewModuleCard>
  );
}
