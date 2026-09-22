/**
 * The bottom drawer: Positions / Orders · today / Nova OS with the status
 * chips on the tab row, the collapse chevron at the right and the open
 * position in the footer (approved Trader redesign, 2026-09-21; WID-019 /
 * 026 / 027 data and actions unchanged). Shared with the Scanner desk.
 */
import { useEffect, useState } from 'react';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import {
  ORDERS_TODAY_TITLE,
  STOCK_VIEW_MODULE_NOVA_OS_TITLE,
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  type StockViewDockSurface,
} from '../constants';
import { drawerSampleBanner } from '../constantGroups/trader_chrome';
import { PositionsPanel } from '../ibkr/PositionsPanel';
import type {
  IbkrAccountSummary,
  IbkrMode,
  IbkrOrder,
  IbkrPosition,
} from '../ibkr/types';
import { OrdersTodayView } from '../orders_today';
import type { OrdersTodayFilter } from '../orders_today';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import {
  parseDockRequest,
  STOCK_VIEW_DOCK_REQUEST_EVENT,
} from './requestDockSurface';
import { StockViewDockBar } from './StockViewDockBar';
import { StockViewDockFooter } from './StockViewDockFooter';
import {
  initialSampleHidden,
  readCollapsed,
  readFilter,
  readSurface,
  writeCollapsed,
  writeFilter,
  writeSampleHidden,
  writeSurface,
} from './stockViewDockPersist';
import { TraderNovaOsBrain } from './TraderNovaOsBrain';
import { useDrawerDisplay } from './useDrawerDisplay';

type Props = {
  symbol: string;
  orders: IbkrOrder[];
  positions: IbkrPosition[];
  symbolPosition?: IbkrPosition | null;
  summary: IbkrAccountSummary | null;
  /** useIbkrAccount poll failure — disables Flatten on last-good rows. */
  accountError?: string | null;
  mode: IbkrMode;
  connected: boolean;
  spendStatus?: string;
  onSelectSymbol: (symbol: string) => void;
  /** Defaults to onSelectSymbol (Trader tab switch). Scanner passes openStockView. */
  onOpenTrading?: (symbol: string) => void;
  onCancelOrder?: (id: number) => void;
  onFillImmediately?: (order: IbkrOrder) => void;
  onPositionClosed?: () => void;
  highlightOrderId?: number | null;
  onCollapsedChange?: (collapsed: boolean) => void;
  /** Which desk mounted this instance -- keep-alive can leave more than one in the tree. */
  host: 'scanner' | 'trader';
};

export function StockViewOpenOrdersDock({
  symbol,
  orders,
  positions,
  symbolPosition = null,
  summary,
  accountError = null,
  mode,
  connected,
  spendStatus,
  onSelectSymbol,
  onOpenTrading,
  onCancelOrder,
  onFillImmediately,
  onPositionClosed,
  highlightOrderId = null,
  onCollapsedChange,
  host,
}: Props) {
  const sample = useSampleDataOptional();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [sampleHidden, setSampleHidden] = useState(() =>
    initialSampleHidden(Boolean(sample)),
  );
  const [filter, setFilter] = useState<OrdersTodayFilter>(readFilter);
  const [surface, setSurface] = useState<StockViewDockSurface>(readSurface);

  useEffect(() => {
    onCollapsedChange?.(collapsed);
  }, [collapsed, onCollapsedChange]);

  const { orders: closedOrders } = useClosedOrders(connected);

  const symbolKey = symbol.toUpperCase();
  // The sample, the rows shown and every count (QA V22): useDrawerDisplay.
  const { wantsWorkingSample, usingSample, displayOrders, displayClosed, openCount, filterCounts } =
    useDrawerDisplay({ surface, filter, orders, closedOrders, sampleHidden, symbolKey });
  const positionCount = positions.length;

  useEffect(() => {
    if (
      highlightOrderId != null ||
      orders.length > 0 ||
      closedOrders.length > 0 ||
      usingSample ||
      positions.length > 0
    ) {
      setCollapsed(false);
      writeCollapsed(false);
    }
  }, [
    highlightOrderId,
    orders.length,
    closedOrders.length,
    usingSample,
    positions.length,
  ]);

  useEffect(() => {
    const onReq = (event: Event) => {
      const req = parseDockRequest((event as CustomEvent).detail);
      if (!req) return;
      if (req.filter) {
        setFilter(req.filter);
        writeFilter(req.filter);
      }
      setSurface(req.surface);
      writeSurface(req.surface);
      setCollapsed(false);
      writeCollapsed(false);
    };
    window.addEventListener(STOCK_VIEW_DOCK_REQUEST_EVENT, onReq);
    return () => window.removeEventListener(STOCK_VIEW_DOCK_REQUEST_EVENT, onReq);
  }, []);

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      writeCollapsed(next);
      return next;
    });
  };

  const expand = () => {
    setCollapsed(false);
    writeCollapsed(false);
  };

  const selectFilter = (next: OrdersTodayFilter) => {
    setFilter(next);
    writeFilter(next);
    expand();
  };

  const selectSurface = (next: StockViewDockSurface) => {
    setSurface(next);
    writeSurface(next);
    expand();
  };

  const hideSample = () => {
    setSampleHidden(true);
    writeSampleHidden(true);
  };

  const showSample = () => {
    setSampleHidden(false);
    writeSampleHidden(false);
    expand();
  };

  const sampleToggle =
    surface !== 'orders'
      ? null
      : usingSample
        ? 'hide'
        : wantsWorkingSample && orders.length === 0
          ? 'show'
          : null;

  return (
    <section
      className={`sv-open-orders-dock${collapsed ? ' sv-open-orders-dock--collapsed' : ''}${
        usingSample ? ' sv-open-orders-dock--sample' : ''
      }`}
      data-testid="stock-view-open-orders-dock"
      data-dock-host={host}
      data-dock-symbol={symbolKey}
      data-dock-surface={surface}
      data-orders-filter={filter}
      data-sample={usingSample ? '1' : undefined}
      aria-label={
        surface === 'positions'
          ? STOCK_VIEW_MODULE_POSITIONS_TITLE
          : surface === 'nova_os'
            ? STOCK_VIEW_MODULE_NOVA_OS_TITLE
            : ORDERS_TODAY_TITLE
      }
    >
      <StockViewDockBar
        surface={surface}
        filter={filter}
        positionCount={positionCount}
        openCount={openCount}
        filterCounts={filterCounts}
        collapsed={collapsed}
        usingSample={usingSample}
        sampleToggle={sampleToggle}
        onSelectSurface={selectSurface}
        onSelectFilter={selectFilter}
        onToggle={toggle}
        onShowSample={showSample}
        onHideSample={hideSample}
      />
      {!collapsed && (
        <>
          <div className="sv-open-orders-dock__body">
            {surface === 'positions' ? (
              <div data-testid="stock-view-positions">
                <PositionsPanel
                  summary={summary}
                  positions={positions}
                  orders={[]}
                  error={accountError}
                  selectedSymbol={symbolKey}
                  onSelectSymbol={onSelectSymbol}
                  onOpenTrading={onOpenTrading ?? onSelectSymbol}
                  mode={mode}
                  connected={connected}
                  spendStatus={spendStatus}
                  onPositionClosed={onPositionClosed}
                  compact
                  hideTitle
                />
              </div>
            ) : surface === 'nova_os' ? (
              <div data-testid="stock-view-nova-os">
                <TraderNovaOsBrain symbol={symbolKey} position={symbolPosition} />
              </div>
            ) : (
              <>
                {usingSample && (
                  <p className="sv-open-orders-dock__banner" role="status" data-testid="stock-view-open-orders-sample-banner">
                    {drawerSampleBanner(mode)}
                  </p>
                )}
                <OrdersTodayView
                  symbol={symbolKey}
                  workingOrders={displayOrders}
                  usingWorkingSample={usingSample}
                  closedOrders={displayClosed}
                  onCancelOrder={onCancelOrder}
                  onFillImmediately={onFillImmediately}
                  highlightOrderId={highlightOrderId}
                  filter={filter}
                  onFilterChange={selectFilter}
                  hideFilters
                />
              </>
            )}
          </div>
          <StockViewDockFooter symbol={symbolKey} mode={mode} position={symbolPosition} />
        </>
      )}
    </section>
  );
}
