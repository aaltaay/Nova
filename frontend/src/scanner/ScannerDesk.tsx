/**
 * Scanner middle stack: selected table on top, Trader account dock below.
 * Same Positions / Orders (Today) strip (WID-019 / 026 / 027). Bots > LiveTrader Bots mounts the same stack around
 * the hosts' page (`host="bots"`, its own split; operator ask 2026-10-16).
 */
import { useCallback, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ResizeHandle } from '../components/ResizeHandle';
import {
  LT_BOTS_ACCOUNT_DOCK_SPLIT_KEY,
  SCANNER_ACCOUNT_DOCK_RESIZE_LABEL,
  SCANNER_ACCOUNT_DOCK_SPLIT_KEY,
  SCANNER_ACCOUNT_DOCK_SPLIT_MAX_PCT,
  SCANNER_ACCOUNT_DOCK_SPLIT_MIN_PCT,
  SCANNER_ACCOUNT_DOCK_SPLIT_PCT,
  STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  STOCK_VIEW_OPEN_ORDERS_PANE_MIN_PX,
} from '../constants';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { cancelIbkrOrderWithFeedback } from '../ibkr';
import { confirmAndFillWorkingOrder } from '../ibkr';
import type { IbkrOrder } from '../ibkr';
import { useTopOfBook } from '../hotkeys';
import { useIbkrAccount } from '../ibkr';
import { useIbkrStatus } from '../ibkr';
import { StockViewOpenOrdersDock } from '../stock_view/StockViewOpenOrdersDock';
import { alertApp } from '../ux';
import { useWorkspace } from '../workspace';

type Props = {
  children: ReactNode;
  /** Sample desk opens Trader via URL; live desk uses workspace.openStockView. */
  onOpenTrading?: (symbol: string) => void;
  /** Which page mounts it (the dock's `data-dock-host`); each keeps its own split. */
  host?: 'scanner' | 'bots';
};

export function ScannerDesk({ children, onOpenTrading, host = 'scanner' }: Props) {
  const { selectedSymbol, openStockView, selectRowSymbol } = useWorkspace();
  const { topOfBook } = useTopOfBook();
  const ibkrStatus = useIbkrStatus();
  const {
    summary,
    positions,
    orders,
    error: accountError,
    refresh,
  } = useIbkrAccount(ibkrStatus.connected);
  const [ordersCollapsed, setOrdersCollapsed] = useState(
    STOCK_VIEW_OPEN_ORDERS_DEFAULT_COLLAPSED,
  );
  const deskRef = useRef<HTMLDivElement>(null);
  const {
    topPct,
    onDragStart,
    reset,
  } = useResizableHeight({
    storageKey: host === 'bots' ? LT_BOTS_ACCOUNT_DOCK_SPLIT_KEY : SCANNER_ACCOUNT_DOCK_SPLIT_KEY,
    defaultPct: SCANNER_ACCOUNT_DOCK_SPLIT_PCT,
    minPct: SCANNER_ACCOUNT_DOCK_SPLIT_MIN_PCT,
    maxPct: SCANNER_ACCOUNT_DOCK_SPLIT_MAX_PCT,
    containerRef: deskRef,
  });

  const symbol = (selectedSymbol ?? '').toUpperCase();
  const symbolPosition =
    positions.find((p) => p.symbol.toUpperCase() === symbol) ?? null;
  const openTrader = onOpenTrading ?? openStockView;

  const onCancelOrder = useCallback(
    async (orderId: number) => {
      await cancelIbkrOrderWithFeedback(orderId, refresh);
    },
    [refresh],
  );

  const onFillImmediately = useCallback(
    async (order: IbkrOrder) => {
      const res = await confirmAndFillWorkingOrder(order, { book: topOfBook });
      if (!res.ok && res.error !== 'Fill now cancelled') {
        void alertApp({ title: 'Fill now failed', message: res.error, tone: 'danger' });
      }
      refresh();
    },
    [refresh, topOfBook],
  );

  return (
    <div
      ref={deskRef}
      className={`scanner-desk${ordersCollapsed ? ' scanner-desk--orders-collapsed' : ''}`}
      style={
        {
          ['--sv-main-pct']: `${topPct}%`,
          ['--sv-orders-pane-min']: `${STOCK_VIEW_OPEN_ORDERS_PANE_MIN_PX}px`,
        } as CSSProperties
      }
      data-testid="scanner-desk"
    >
      <div className="scanner-desk__tables">{children}</div>
      {!ordersCollapsed && (
        <ResizeHandle
          orientation="horizontal"
          onPointerDown={onDragStart}
          onDoubleClick={reset}
          label={SCANNER_ACCOUNT_DOCK_RESIZE_LABEL}
        />
      )}
      <StockViewOpenOrdersDock
        host={host}
        symbol={symbol}
        orders={orders}
        positions={positions}
        symbolPosition={symbolPosition}
        summary={summary}
        accountError={accountError}
        mode={ibkrStatus.mode}
        connected={ibkrStatus.connected}
        spendStatus={ibkrStatus.spend_status}
        onSelectSymbol={selectRowSymbol}
        onOpenTrading={openTrader}
        onCancelOrder={onCancelOrder}
        onFillImmediately={onFillImmediately}
        onPositionClosed={refresh}
        onCollapsedChange={setOrdersCollapsed}
      />
    </div>
  );
}
