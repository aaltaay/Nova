/**
 * Scanner middle stack: selected table on top, Trader account dock below.
 * Same Positions / Orders (Today) / Nova OS strip (WID-019 / 026 / 027).
 */
import { useCallback, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ResizeHandle } from '../components/ResizeHandle';
import {
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
import { confirmAndFillWorkingOrder } from '../ibkr/fillWorkingOrderImmediately';
import type { IbkrOrder } from '../ibkr/types';
import { useIbkrAccount } from '../ibkr/useIbkrAccount';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { StockViewOpenOrdersDock } from '../stock_view/StockViewOpenOrdersDock';
import { alertApp } from '../ux';
import { useWorkspace } from '../workspace/WorkspaceContext';

type Props = {
  children: ReactNode;
  /** Sample desk opens Trader via URL; live desk uses workspace.openStockView. */
  onOpenTrading?: (symbol: string) => void;
};

export function ScannerDesk({ children, onOpenTrading }: Props) {
  const { selectedSymbol, openStockView, selectRowSymbol } = useWorkspace();
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
    storageKey: SCANNER_ACCOUNT_DOCK_SPLIT_KEY,
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
      const res = await confirmAndFillWorkingOrder(order);
      if (!res.ok && res.error !== 'Fill now cancelled') {
        void alertApp({ title: 'Fill now failed', message: res.error, tone: 'danger' });
      }
      refresh();
    },
    [refresh],
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
