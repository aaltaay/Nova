/** Last + change row for Stock Quote (replaces the old Trader header chip). */
import type { TickerDetail } from '../types/ticker';
import { fmtPct } from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from '../modules/quoteMetrics';

interface Props {
  detail: TickerDetail;
}

export function StockViewQuotePrice({ detail }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);

  return (
    <div className="sv-quote-card__price" data-testid="stock-view-quote-price">
      <span className="sv-quote-card__symbol">{detail.symbol}</span>
      {m.mainPrice != null ? (
        <span className="sv-quote-card__last">${m.mainPrice.toFixed(2)}</span>
      ) : (
        <span className="sv-quote-card__last sv-quote-card__last--missing" title="Waiting for IBKR quote">
          --
        </span>
      )}
      {m.mainChangeAbs != null ? (
        <span
          className={`sv-quote-card__chg ${(m.mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
        >
          {m.mainChangeAbs >= 0 ? '+' : ''}
          {m.mainChangeAbs.toFixed(2)} ({fmtPct(m.mainChangePct)})
        </span>
      ) : null}
    </div>
  );
}
