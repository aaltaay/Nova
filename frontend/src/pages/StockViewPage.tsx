/**
 * Stock View — detachable terminal page (double-click → new window).
 *
 * Thin data coordinator: streams, IBKR gates, resizable rail, detached nav.
 * Layout chrome lives under `stock_view/` (header + rail + quote card).
 */
import { useCallback, useEffect, useState } from 'react';
import { ChartGrid } from '../components/ChartGrid';
import { ResizeHandle } from '../components/ResizeHandle';
import { useResizableWidth } from '../hooks/useResizableWidth';
import { useTickerStream } from '../hooks/useTickerStream';
import { useIbkrAccount } from '../ibkr/useIbkrAccount';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { novaFetch } from '../api/novaFetch';
import type { PlaceOrderResult } from '../ibkr/placeOrder';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { StockViewHeader } from '../stock_view/StockViewHeader';
import { StockViewOpenOrdersDock } from '../stock_view/StockViewOpenOrdersDock';
import { StockViewRail } from '../stock_view/StockViewRail';
import {
  API_BASE_URL,
  STOCK_VIEW_SIDE_WIDTH_KEY,
  STOCK_VIEW_TITLE,
  TICKER_TRADE_SIDE_WIDTH_MAX_PX,
  TICKER_TRADE_SIDE_WIDTH_MIN_PX,
  TICKER_TRADE_SIDE_WIDTH_PX,
} from '../constants';
import { replaceStockViewUrl } from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';

interface Props {
  symbol: string;
  /** True when this page was opened as ?view=stock (standalone tab). */
  detached?: boolean;
  /** Kept for App router compatibility; header no longer exposes Close/Back. */
  onBack: () => void;
  onSelectSymbol: (symbol: string) => void;
}

export function StockViewPage({
  symbol,
  detached = false,
  onSelectSymbol,
}: Props) {
  const { discoveryProvider } = useWorkspace();
  const { detail, loading, refreshing, fetchFailed } = useTickerStream(symbol);
  const ibkrStatus = useIbkrStatus();
  const { summary, positions, orders, refresh } = useIbkrAccount(ibkrStatus.connected);
  const [highlightOrderId, setHighlightOrderId] = useState<number | null>(null);
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

  const detailReady = detail != null && detail.symbol.toUpperCase() === symbol.toUpperCase();
  const showSpinner = (loading || refreshing || (!detailReady && !fetchFailed)) && !detailReady;
  const metrics = detailReady && detail ? computeQuoteMetrics(detail, discoveryProvider) : null;
  const lastTrade =
    detailReady && detail?.snapshot?.latest_trade?.price != null
      ? {
          price: detail.snapshot.latest_trade.price,
          timestamp: detail.snapshot.latest_trade.timestamp ?? null,
        }
      : undefined;

  const symbolPosition =
    positions.find(p => p.symbol.toUpperCase() === symbol.toUpperCase()) ?? null;

  const onOrderPlaced = useCallback(
    (result?: PlaceOrderResult) => {
      if (result?.ok && result.order_id != null) {
        setHighlightOrderId(result.order_id);
      }
      refresh();
    },
    [refresh],
  );

  const onCancelOrder = useCallback(
    async (orderId: number) => {
      try {
        await novaFetch(`${API_BASE_URL}/api/ibkr/order/${orderId}`, { method: 'DELETE' });
        refresh();
      } catch {
        // next poll retries
      }
    },
    [refresh],
  );

  const handleLookup = useCallback(
    (next: string) => {
      if (detached) replaceStockViewUrl(next);
      onSelectSymbol(next);
    },
    [detached, onSelectSymbol],
  );

  return (
    <div
      className="stock-view-page"
      style={{ ['--ticker-trade-side-width' as string]: `${sideWidth}px` }}
    >
      <StockViewHeader
        symbol={symbol}
        detailReady={detailReady}
        detailSymbol={detail?.symbol}
        mainPrice={metrics?.mainPrice ?? null}
        mainChangeAbs={metrics?.mainChangeAbs ?? null}
        mainChangePct={metrics?.mainChangePct ?? null}
        isPositive={metrics?.isPositive ?? true}
        refreshing={refreshing}
        mode={ibkrStatus.mode}
        connected={ibkrStatus.connected}
        summary={summary}
        onLookup={handleLookup}
      />

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
            <div className="stock-view-main">
              <div className="stock-view-charts">
                <ChartGrid symbol={symbol} lastTrade={lastTrade} />
              </div>
            </div>
            <ResizeHandle
              onPointerDown={onSideResizeStart}
              onDoubleClick={resetSideWidth}
              label="Resize trading rail"
            />
            <StockViewRail
              symbol={symbol}
              detail={detail}
              mode={ibkrStatus.mode}
              connected={ibkrStatus.connected}
              spendStatus={ibkrStatus.spend_status}
              position={symbolPosition}
              summary={summary}
              referencePrice={metrics?.mainPrice ?? null}
              onOrderPlaced={onOrderPlaced}
            />
          </div>
          <StockViewOpenOrdersDock
            symbol={symbol}
            orders={orders}
            onCancelOrder={onCancelOrder}
            highlightOrderId={highlightOrderId}
          />
        </>
      )}
    </div>
  );
}
