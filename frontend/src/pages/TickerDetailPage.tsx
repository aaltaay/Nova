/** Full-page ticker trading view — replaces the scanner when a symbol is selected. */
import { TickerChart } from '../TickerChart';
import { TickerDetailContent } from '../components/TickerDetailContent';
import { useTickerStream } from '../hooks/useTickerStream';
import { fmtPct } from '../utils/quoteFormat';

interface Props {
  symbol: string;
  onBack: () => void;
  onSelectSymbol: (symbol: string) => void;
}

export function TickerDetailPage({ symbol, onBack, onSelectSymbol }: Props) {
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(symbol);
  const snap = detail?.snapshot;
  const trade = snap?.latest_trade;
  const daily = snap?.daily_bar;
  const prevClose = snap?.prev_close ?? snap?.prev_daily_bar?.close ?? null;
  const isExtendedHours = detail?.mode === 'premarket' || detail?.mode === 'afterhours';
  const sessionClose = snap?.session_close ?? null;
  const sessionPrevClose = snap?.session_prev_close ?? null;
  const livePrice = trade?.price ?? daily?.close ?? null;
  const mainPrice = isExtendedHours ? sessionClose : livePrice;
  const mainPrevRef = isExtendedHours ? sessionPrevClose : prevClose;
  const mainChangeAbs = (mainPrice != null && mainPrevRef != null) ? mainPrice - mainPrevRef : null;
  const mainChangePct = (mainChangeAbs != null && mainPrevRef) ? mainChangeAbs / mainPrevRef : null;
  const isPositive = (mainChangePct ?? 0) >= 0;

  const showSpinner = (loading || (!detail && !fetchFailed)) && !detail;

  return (
    <div className="ticker-detail-page">
      <div className="ticker-detail-toolbar">
        <button type="button" className="ticker-detail-back" onClick={onBack} title="Return to the scanner">
          ← Back
        </button>
        <form
          className="ticker-detail-lookup"
          onSubmit={(e) => {
            e.preventDefault();
            const fd = new FormData(e.currentTarget);
            const next = String(fd.get('symbol') ?? '').trim().toUpperCase();
            if (next) onSelectSymbol(next);
          }}
        >
          <input
            name="symbol"
            className="side-search-input"
            type="text"
            defaultValue={symbol}
            key={symbol}
            placeholder="Symbol, e.g. AAPL"
            autoComplete="off"
            spellCheck={false}
            aria-label="Look up symbol"
          />
          <button type="submit" className="side-search-btn">Look Up</button>
        </form>
      </div>

      {showSpinner && (
        <div className="detail-loading">
          <div className="detail-loading-spinner" />
          <span>Loading {symbol}…</span>
        </div>
      )}

      {fetchFailed && !detail && (
        <div className="empty-state">No data found for {symbol}.</div>
      )}

      {detail && (
        <>
          <header className="ticker-detail-header">
            <div className="cq-symbol-row">
              <span className="cq-symbol">{detail.symbol}</span>
              {mainChangeAbs != null && (
                <span className="cq-trend">{isPositive ? '▲' : '▼'}</span>
              )}
              {refreshing && <span className="na-muted ticker-detail-refreshing">Updating…</span>}
            </div>
            {mainPrice != null && (
              <div className="cq-price-row">
                <span className="cq-price">{mainPrice.toFixed(2)}</span>
                {mainChangeAbs != null && (
                  <span className={`cq-change ${(mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}>
                    {mainChangeAbs >= 0 ? '+' : ''}{mainChangeAbs.toFixed(2)} ({fmtPct(mainChangePct)})
                  </span>
                )}
              </div>
            )}
          </header>

          <TickerChart
            symbol={detail.symbol}
            variant="page"
            lastTrade={trade?.price != null ? { price: trade.price, timestamp: trade.timestamp ?? null } : undefined}
          />

          <TickerDetailContent detail={detail} hideHeader />
        </>
      )}
    </div>
  );
}
