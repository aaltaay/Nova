/** Full-page ticker trading view — opened via double-click (or Full view); Back returns to scanner.
 *
 * Layout: charts (primary 2×2) | compact side info | bottom Open / Close / Automate bar.
 */
import { useCallback } from 'react';
import { ChartGrid } from '../components/ChartGrid';
import { useTickerStream } from '../hooks/useTickerStream';
import { TICKER_TRADE_SIDE_WIDTH_PX } from '../constants';
import { TickerTradeActionBar } from '../ibkr/TickerTradeActionBar';
import { TickerTradeSideColumn } from '../ibkr/TickerTradeSideColumn';
import { useIbkrAccount } from '../ibkr/useIbkrAccount';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { fmtPct } from '../utils/quoteFormat';

interface Props {
  symbol: string;
  onBack: () => void;
  onSelectSymbol: (symbol: string) => void;
}

export function TickerDetailPage({ symbol, onBack, onSelectSymbol }: Props) {
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(symbol);
  const ibkrStatus = useIbkrStatus();
  const { summary, positions, refresh } = useIbkrAccount(ibkrStatus.connected);

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
  const mainChangeAbs =
    mainPrice != null && mainPrevRef != null ? mainPrice - mainPrevRef : null;
  const mainChangePct =
    mainChangeAbs != null && mainPrevRef ? mainChangeAbs / mainPrevRef : null;
  const isPositive = (mainChangePct ?? 0) >= 0;

  const showSpinner = (loading || (!detail && !fetchFailed)) && !detail;
  const lastTrade =
    trade?.price != null
      ? { price: trade.price, timestamp: trade.timestamp ?? null }
      : undefined;

  const symbolPosition =
    positions.find((p) => p.symbol.toUpperCase() === symbol.toUpperCase()) ?? null;

  const onOrderPlaced = useCallback(() => {
    refresh();
  }, [refresh]);

  return (
    <div
      className="ticker-detail-page ticker-detail-page--trading"
      style={{ ['--ticker-trade-side-width' as string]: `${TICKER_TRADE_SIDE_WIDTH_PX}px` }}
    >
      <div className="ticker-detail-toolbar">
        <button
          type="button"
          className="ticker-detail-back"
          onClick={onBack}
          title="Return to the scanner"
        >
          ← Back
        </button>
        {detail && (
          <header className="ticker-detail-header">
            <div className="cq-symbol-row">
              <span className="cq-symbol">{detail.symbol}</span>
              {mainChangeAbs != null && (
                <span className="cq-trend">{isPositive ? '▲' : '▼'}</span>
              )}
              {refreshing && (
                <span className="na-muted ticker-detail-refreshing">Updating…</span>
              )}
            </div>
            {mainPrice != null && (
              <div className="cq-price-row">
                <span className="cq-price">{mainPrice.toFixed(2)}</span>
                {mainChangeAbs != null && (
                  <span
                    className={`cq-change ${(mainChangePct ?? 0) >= 0 ? 'positive' : 'negative'}`}
                  >
                    {mainChangeAbs >= 0 ? '+' : ''}
                    {mainChangeAbs.toFixed(2)} ({fmtPct(mainChangePct)})
                  </span>
                )}
              </div>
            )}
          </header>
        )}
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
          <button type="submit" className="side-search-btn">
            Look Up
          </button>
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
          <div className="ticker-trade-body">
            <div className="ticker-trade-charts">
              <ChartGrid symbol={detail.symbol} lastTrade={lastTrade} />
            </div>
            <TickerTradeSideColumn
              detail={detail}
              position={symbolPosition}
              ibkrConnected={ibkrStatus.connected}
              mode={ibkrStatus.mode}
            />
          </div>

          <TickerTradeActionBar
            symbol={detail.symbol}
            mode={ibkrStatus.mode}
            connected={ibkrStatus.connected}
            position={symbolPosition}
            summary={summary}
            onOrderPlaced={onOrderPlaced}
          />
        </>
      )}
    </div>
  );
}
