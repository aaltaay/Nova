/**
 * Stock View — detachable terminal page (double-click → new window).
 *
 * Thin data coordinator: streams, IBKR gates, resizable rail, detached nav.
 * Layout chrome lives under `stock_view/` (header + rail + quote card).
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { ChartGrid } from '../components/ChartGrid';
import { ResizeHandle } from '../components/ResizeHandle';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { useResizableWidth } from '../hooks/useResizableWidth';
import { useTickerStream } from '../hooks/useTickerStream';
import { useIbkrAccount } from '../ibkr/useIbkrAccount';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { cancelIbkrOrderWithFeedback } from '../ibkr';
import { confirmAndFillWorkingOrder } from '../ibkr/fillWorkingOrderImmediately';
import type { PlaceOrderResult } from '../ibkr/placeOrder';
import type { IbkrOrder } from '../ibkr/types';
import { computeQuoteMetrics } from '../modules/quoteMetrics';
import { StockViewHeader } from '../stock_view/StockViewHeader';
import { StockViewOpenOrdersDock } from '../stock_view/StockViewOpenOrdersDock';
import { StockViewRail } from '../stock_view/StockViewRail';
import {
  STOCK_VIEW_MAIN_ORDERS_SPLIT_KEY,
  STOCK_VIEW_MAIN_ORDERS_SPLIT_MAX_PCT,
  STOCK_VIEW_MAIN_ORDERS_SPLIT_MIN_PCT,
  STOCK_VIEW_MAIN_ORDERS_SPLIT_PCT,
  STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  STOCK_VIEW_OPEN_ORDERS_PANE_MIN_PX,
  STOCK_VIEW_SIDE_WIDTH_KEY,
  STOCK_VIEW_TITLE,
  TICKER_TRADE_SIDE_WIDTH_MAX_PX,
  TICKER_TRADE_SIDE_WIDTH_MIN_PX,
  TICKER_TRADE_SIDE_WIDTH_PX,
} from '../constants';
import { replaceStockViewUrl } from '../utils/stockViewNav';
import { alertApp } from '../ux';
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
  const {
    summary,
    positions,
    orders,
    error: accountError,
    refresh,
  } = useIbkrAccount(ibkrStatus.connected);
  const [highlightOrderId, setHighlightOrderId] = useState<number | null>(null);
  const [ordersCollapsed, setOrdersCollapsed] = useState(
    STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  );
  /** Left column (charts + Orders) — height split is relative to this pane. */
  const mainColRef = useRef<HTMLDivElement>(null);
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
  const {
    topPct: mainPct,
    onDragStart: onMainOrdersResizeStart,
    reset: resetMainOrdersSplit,
  } = useResizableHeight({
    storageKey: STOCK_VIEW_MAIN_ORDERS_SPLIT_KEY,
    defaultPct: STOCK_VIEW_MAIN_ORDERS_SPLIT_PCT,
    minPct: STOCK_VIEW_MAIN_ORDERS_SPLIT_MIN_PCT,
    maxPct: STOCK_VIEW_MAIN_ORDERS_SPLIT_MAX_PCT,
    containerRef: mainColRef,
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
      await cancelIbkrOrderWithFeedback(orderId, refresh);
    },
    [refresh],
  );

  const onFillImmediately = useCallback(
    async (order: IbkrOrder) => {
      const res = await confirmAndFillWorkingOrder(order);
      if (res.ok && res.place_order_id != null) {
        setHighlightOrderId(res.place_order_id);
      }
      if (!res.ok && res.error !== 'Fill now cancelled') {
        void alertApp({ title: 'Fill now failed', message: res.error, tone: 'danger' });
      }
      refresh();
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
        gatewayMode={ibkrStatus.gateway_mode}
        connected={ibkrStatus.connected}
        ibkrStatus={ibkrStatus}
        summary={summary}
        onLookup={handleLookup}
      />

      {/*
        Positions / Orders / Nova OS dock must not wait on ticker WS — account
        tables stay usable while charts/rail load (also keeps e2e stable).
      */}
      <div
        className="stock-view-workspace"
        data-testid="stock-view-workspace"
      >
        <div className="stock-view-body">
          <div
            ref={mainColRef}
            className={`stock-view-main${
              ordersCollapsed ? ' stock-view-main--orders-collapsed' : ''
            }`}
            style={
              {
                ['--sv-main-pct']: `${mainPct}%`,
                ['--sv-orders-pane-min']: `${STOCK_VIEW_OPEN_ORDERS_PANE_MIN_PX}px`,
              } as CSSProperties
            }
            data-testid="stock-view-main"
          >
            <div className="stock-view-charts">
              {detailReady && detail ? (
                <ChartGrid symbol={symbol} lastTrade={lastTrade} />
              ) : showSpinner ? (
                <div className="detail-loading">
                  <div className="detail-loading-spinner" />
                  <span>Loading {symbol}…</span>
                </div>
              ) : fetchFailed ? (
                <div className="empty-state">No data found for {symbol}.</div>
              ) : null}
            </div>
            {!ordersCollapsed && (
              <ResizeHandle
                orientation="horizontal"
                onPointerDown={onMainOrdersResizeStart}
                onDoubleClick={resetMainOrdersSplit}
                label="Resize charts and Orders"
              />
            )}
            <StockViewOpenOrdersDock
              symbol={symbol}
              orders={orders}
              positions={positions}
              symbolPosition={symbolPosition}
              summary={summary}
              accountError={accountError}
              mode={ibkrStatus.mode}
              connected={ibkrStatus.connected}
              spendStatus={ibkrStatus.spend_status}
              onSelectSymbol={onSelectSymbol}
              onCancelOrder={onCancelOrder}
              onFillImmediately={onFillImmediately}
              onPositionClosed={refresh}
              highlightOrderId={highlightOrderId}
              onCollapsedChange={setOrdersCollapsed}
            />
          </div>
          <ResizeHandle
            onPointerDown={onSideResizeStart}
            onDoubleClick={resetSideWidth}
            label="Resize trading rail"
          />
          {detailReady && detail ? (
            <StockViewRail
              symbol={symbol}
              detail={detail}
              mode={ibkrStatus.mode}
              connected={ibkrStatus.connected}
              spendStatus={ibkrStatus.spend_status}
              accountError={accountError}
              position={symbolPosition}
              summary={summary}
              referencePrice={metrics?.mainPrice ?? null}
              onOrderPlaced={onOrderPlaced}
            />
          ) : (
            <aside
              className="stock-view-rail stock-view-rail--pending"
              aria-busy={!fetchFailed}
              data-testid="stock-view-rail-pending"
            />
          )}
        </div>
      </div>
    </div>
  );
}
