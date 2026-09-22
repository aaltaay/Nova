/**
 * Last + change row for Stock Quote (replaces the old Trader header chip).
 *
 * Off the live edge a Sim tab shows the replay's price at the playhead
 * (`useReplayQuote`): the ticker stream is not re-seeded on a seek, so reading
 * it froze the head at the price the tab opened on (QA 2026-09-22, R10). In a
 * gap in the recording, or with nothing loaded for this tab, the head says so
 * instead of showing a price.
 */
import type { TickerDetail } from '../types/ticker';
import { fmtPct } from '../utils/quoteFormat';
import { useWorkspace } from '../workspace';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { useReplayQuote } from '../sim/useReplayQuote';

interface Props {
  detail: TickerDetail;
}

export function StockViewQuotePrice({ detail }: Props) {
  const { discoveryProvider } = useWorkspace();
  const m = computeQuoteMetrics(detail, discoveryProvider);
  const replay = useReplayQuote(detail.symbol);
  const price = replay.active ? replay.last : m.mainPrice;
  const prev = replay.active ? replay.prevClose : null;
  const changeAbs = replay.active ? (price != null && prev != null ? price - prev : null) : m.mainChangeAbs;
  const changePct = replay.active ? (changeAbs != null && prev ? changeAbs / prev : null) : m.mainChangePct;

  return (
    <div className="sv-quote-card__price" data-testid="stock-view-quote-price">
      <span className="sv-quote-card__symbol">{detail.symbol}</span>
      {price != null ? (
        <span className="sv-quote-card__last">${price.toFixed(2)}</span>
      ) : (
        <span
          className="sv-quote-card__last sv-quote-card__last--missing"
          title={replay.active ? replay.note ?? undefined : 'Waiting for IBKR quote'}
          data-testid="stock-view-quote-missing"
        >
          --
        </span>
      )}
      {changeAbs != null ? (
        <span
          className={`sv-quote-card__chg ${(changePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
        >
          {changeAbs >= 0 ? '+' : ''}
          {changeAbs.toFixed(2)} ({fmtPct(changePct)})
        </span>
      ) : null}
    </div>
  );
}
