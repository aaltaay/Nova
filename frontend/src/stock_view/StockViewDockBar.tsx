/**
 * The drawer's one tab row (approved Trader redesign, 2026-09-21):
 * `Positions N · Orders · today N`, the Working / Filled / Canceled /
 * Partial / All chips on the same row while Orders is showing, then the
 * sample toggle and the collapse chevron at the right. Clicking bare bar
 * space toggles the drawer, as before.
 */
import type { MouseEvent } from 'react';
import {
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  type OrdersTodayFilterId,
  type StockViewDockSurface,
} from '../constants';
import {
  DRAWER_COLLAPSE,
  DRAWER_EXPAND,
  DRAWER_SAMPLE_HIDE,
  DRAWER_SAMPLE_SHOW,
  DRAWER_SAMPLE_TAG,
  DRAWER_TAB_ORDERS,
  DRAWER_TABS_ARIA,
} from '../constantGroups/trader_chrome';
import { OrdersTodayFilters } from '../orders_today';

type Props = {
  surface: StockViewDockSurface;
  filter: OrdersTodayFilterId;
  positionCount: number;
  openCount: number;
  /** Count behind each status chip (the badge count for that filter). */
  filterCounts: Partial<Record<OrdersTodayFilterId, number>>;
  collapsed: boolean;
  usingSample: boolean;
  /** Which sample affordance the Orders surface offers right now, if any. */
  sampleToggle: 'show' | 'hide' | null;
  onSelectSurface: (surface: StockViewDockSurface) => void;
  onSelectFilter: (filter: OrdersTodayFilterId) => void;
  onToggle: () => void;
  onShowSample: () => void;
  onHideSample: () => void;
};

function Tab({
  active,
  testId,
  onClick,
  children,
}: {
  active: boolean;
  testId: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={active ? 'sv-open-orders-dock__tab is-active' : 'sv-open-orders-dock__tab'}
      data-testid={testId}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function StockViewDockBar({
  surface,
  filter,
  positionCount,
  openCount,
  filterCounts,
  collapsed,
  usingSample,
  sampleToggle,
  onSelectSurface,
  onSelectFilter,
  onToggle,
  onShowSample,
  onHideSample,
}: Props) {
  const onBarClick = (event: MouseEvent<HTMLElement>) => {
    const el = event.target as HTMLElement;
    if (el.closest('button')) return;
    if (el.closest('.sv-open-orders-dock__tabs')) return;
    if (el.closest('.orders-today-filters')) return;
    onToggle();
  };

  return (
    <header className="sv-open-orders-dock__bar" onClick={onBarClick}>
      <div
        className="sv-open-orders-dock__tabs"
        role="tablist"
        aria-label={DRAWER_TABS_ARIA}
        onClick={(e) => e.stopPropagation()}
      >
        <Tab
          active={surface === 'positions'}
          testId="stock-view-dock-tab-positions"
          onClick={() => onSelectSurface('positions')}
        >
          {STOCK_VIEW_MODULE_POSITIONS_TITLE}
          <span className="sv-open-orders-dock__count">{positionCount}</span>
        </Tab>
        <Tab
          active={surface === 'orders'}
          testId="stock-view-dock-tab-orders"
          onClick={() => onSelectSurface('orders')}
        >
          {DRAWER_TAB_ORDERS}
          <span className="sv-open-orders-dock__count">{openCount}</span>
          {usingSample && (
            <span className="sv-open-orders-dock__sample-tag">{DRAWER_SAMPLE_TAG}</span>
          )}
        </Tab>
      </div>
      {surface === 'orders' && (
        <OrdersTodayFilters value={filter} onChange={onSelectFilter} counts={filterCounts} />
      )}
      <div className="sv-open-orders-dock__tools">
        {sampleToggle === 'hide' ? (
          <button
            type="button"
            className="sv-open-orders-dock__sample-btn"
            onClick={onHideSample}
          >
            {DRAWER_SAMPLE_HIDE}
          </button>
        ) : sampleToggle === 'show' ? (
          <button
            type="button"
            className="sv-open-orders-dock__sample-btn"
            onClick={onShowSample}
            data-testid="stock-view-open-orders-show-sample"
          >
            {DRAWER_SAMPLE_SHOW}
          </button>
        ) : null}
        <button
          type="button"
          className="sv-open-orders-dock__toggle"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? DRAWER_EXPAND : DRAWER_COLLAPSE}
          title={collapsed ? DRAWER_EXPAND : DRAWER_COLLAPSE}
          data-testid="stock-view-open-orders-toggle"
        >
          <span className="sv-open-orders-dock__chevron" aria-hidden="true">
            {collapsed ? '▴' : '▾'}
          </span>
        </button>
      </div>
    </header>
  );
}
