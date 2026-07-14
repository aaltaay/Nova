/**
 * Stock View — detachable single-stock page (double-click / new tab).
 *
 * Reuses the same Quote Panel body (`TickerDetailContent`) as the scanner
 * sidebar so fundamentals / broker / data sources stay one-to-one. Adds the
 * 2×2 chart grid (collapsible) and the IBKR Open / Close / Automate bar.
 */
import { useCallback, useEffect, useState } from 'react';
import { ChartGrid } from '../components/ChartGrid';
import { ResizeHandle } from '../components/ResizeHandle';
import { TickerDetailContent } from '../components/TickerDetailContent';
import { useResizableWidth } from '../hooks/useResizableWidth';
import { useTickerStream } from '../hooks/useTickerStream';
import { TickerTradeActionBar } from '../ibkr/TickerTradeActionBar';
import { useIbkrAccount } from '../ibkr/useIbkrAccount';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useWatchlist } from '../strategy/useWatchlist';
import {
  API_BASE_URL,
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
  STOCK_VIEW_CHARTS_COLLAPSED_KEY,
  STOCK_VIEW_CHARTS_HIDE_LABEL,
  STOCK_VIEW_CHARTS_SHOW_LABEL,
  STOCK_VIEW_SIDE_WIDTH_KEY,
  STOCK_VIEW_TITLE,
  TICKER_TRADE_SIDE_WIDTH_MAX_PX,
  TICKER_TRADE_SIDE_WIDTH_MIN_PX,
  TICKER_TRADE_SIDE_WIDTH_PX,
} from '../constants';
import { fmtPct } from '../utils/quoteFormat';
import { replaceStockViewUrl } from '../utils/stockViewNav';

const API_URL = `${API_BASE_URL}/api`;

interface Props {
  symbol: string;
  /** True when this page was opened as ?view=stock (standalone tab). */
  detached?: boolean;
  onBack: () => void;
  onSelectSymbol: (symbol: string) => void;
}

function readChartsCollapsed(): boolean {
  try {
    return localStorage.getItem(STOCK_VIEW_CHARTS_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

export function StockViewPage({
  symbol,
  detached = false,
  onBack,
  onSelectSymbol,
}: Props) {
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(symbol);
  const ibkrStatus = useIbkrStatus();
  const { summary, positions, refresh } = useIbkrAccount(ibkrStatus.connected);
  const watchlist = useWatchlist(true);
  const [chartsCollapsed, setChartsCollapsed] = useState(readChartsCollapsed);
  const [discoveryProvider, setDiscoveryProvider] = useState(DISCOVERY_PROVIDER_DEFAULT);
  const [alpacaFeed, setAlpacaFeed] = useState(DATA_FEED_DEFAULT);
  const {
    width: sideWidth,
    onDragStart: onSideResizeStart,
    reset: resetSideWidth,
  } = useResizableWidth({
    storageKey: STOCK_VIEW_SIDE_WIDTH_KEY,
    defaultPx: TICKER_TRADE_SIDE_WIDTH_PX,
    minPx: TICKER_TRADE_SIDE_WIDTH_MIN_PX,
    maxPx: TICKER_TRADE_SIDE_WIDTH_MAX_PX,
  });

  useEffect(() => {
    document.title = `${symbol} · ${STOCK_VIEW_TITLE} · Nova`;
    return () => {
      document.title = 'Nova — Stock Scanner';
    };
  }, [symbol]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/config`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return;
        if (data.discovery_provider) setDiscoveryProvider(data.discovery_provider);
        if (data.data_feed) setAlpacaFeed(data.data_feed);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleCharts = useCallback(() => {
    setChartsCollapsed(prev => {
      const next = !prev;
      try {
        localStorage.setItem(STOCK_VIEW_CHARTS_COLLAPSED_KEY, next ? '1' : '0');
      } catch {
        /* ignore quota / private mode */
      }
      return next;
    });
  }, []);

  const snap = detail?.snapshot;
  const trade = snap?.latest_trade;
  const daily = snap?.daily_bar;
  const prevClose = snap?.prev_close ?? snap?.prev_daily_bar?.close ?? null;
  // Match TickerDetailContent: IBKR = one live line vs scanner prev_close.
  const useIbkrUnifiedQuote = discoveryProvider === 'ibkr';
  const isExtendedHours =
    !useIbkrUnifiedQuote && (detail?.mode === 'premarket' || detail?.mode === 'afterhours');
  const sessionClose = snap?.session_close ?? null;
  const sessionPrevClose = snap?.session_prev_close ?? null;
  const livePrice = trade?.price ?? daily?.close ?? null;
  const mainPrice = useIbkrUnifiedQuote
    ? livePrice
    : (isExtendedHours ? sessionClose : livePrice);
  const mainPrevRef = useIbkrUnifiedQuote
    ? prevClose
    : (isExtendedHours ? sessionPrevClose : prevClose);
  const mainChangeAbs =
    mainPrice != null && mainPrevRef != null ? mainPrice - mainPrevRef : null;
  const mainChangePct =
    mainChangeAbs != null && mainPrevRef ? mainChangeAbs / mainPrevRef : null;
  const isPositive = (mainChangePct ?? 0) >= 0;

  const detailReady = detail != null && detail.symbol.toUpperCase() === symbol.toUpperCase();
  const showSpinner = (loading || refreshing || (!detailReady && !fetchFailed)) && !detailReady;
  const lastTrade =
    detailReady && trade?.price != null
      ? { price: trade.price, timestamp: trade.timestamp ?? null }
      : undefined;

  const symbolPosition =
    positions.find(p => p.symbol.toUpperCase() === symbol.toUpperCase()) ?? null;
  const watchlistEntry =
    watchlist.entries.find(e => e.symbol.toUpperCase() === symbol.toUpperCase()) ?? null;

  const onOrderPlaced = useCallback(() => {
    refresh();
  }, [refresh]);

  function handleLookup(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const next = String(fd.get('symbol') ?? '').trim().toUpperCase();
    if (!next) return;
    if (detached) replaceStockViewUrl(next);
    onSelectSymbol(next);
  }

  return (
    <div
      className={`stock-view-page${chartsCollapsed ? ' stock-view-page--charts-collapsed' : ''}`}
      style={{ ['--ticker-trade-side-width' as string]: `${sideWidth}px` }}
    >
      <div className="ticker-detail-toolbar stock-view-toolbar">
        <button
          type="button"
          className="ticker-detail-back"
          onClick={onBack}
          title={detached ? 'Close Stock View tab' : 'Return to the scanner'}
        >
          {detached ? '✕ Close' : '← Back'}
        </button>
        <div className="stock-view-brand">
          <span className="stock-view-brand-label">{STOCK_VIEW_TITLE}</span>
          {detailReady && (
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
        </div>
        <button
          type="button"
          className="stock-view-charts-toggle"
          onClick={toggleCharts}
          aria-pressed={!chartsCollapsed}
        >
          {chartsCollapsed ? STOCK_VIEW_CHARTS_SHOW_LABEL : STOCK_VIEW_CHARTS_HIDE_LABEL}
        </button>
        <form className="ticker-detail-lookup" onSubmit={handleLookup}>
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

      {fetchFailed && !detailReady && (
        <div className="empty-state">No data found for {symbol}.</div>
      )}

      {detailReady && detail && (
        <>
          <div className="stock-view-body">
            {!chartsCollapsed && (
              <>
                <div className="stock-view-charts">
                  <ChartGrid symbol={symbol} lastTrade={lastTrade} />
                </div>
                <ResizeHandle
                  onPointerDown={onSideResizeStart}
                  onDoubleClick={resetSideWidth}
                  label="Resize quote panel"
                />
              </>
            )}
            <div className="stock-view-quote" aria-label={STOCK_VIEW_TITLE}>
              <TickerDetailContent
                detail={detail}
                selectedSymbol={symbol}
                showChart={false}
                layout="columns"
                watchlistEntry={watchlistEntry}
                ibkrConnected={ibkrStatus.connected}
                discoveryProvider={discoveryProvider}
                alpacaFeed={alpacaFeed}
              />
            </div>
          </div>

          <TickerTradeActionBar
            symbol={symbol}
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
