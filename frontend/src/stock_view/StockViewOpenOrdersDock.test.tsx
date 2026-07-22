/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ORDERS_TODAY_TITLE,
  STOCK_VIEW_MODULE_NOVA_OS_TITLE,
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY,
} from '../constants';
import type { ClosedOrder } from '../closed_orders/types';
import type { IbkrOrder, IbkrPosition } from '../ibkr/types';
import { StockViewOpenOrdersDock } from './StockViewOpenOrdersDock';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: false, mode: 'paper' }),
}));

// `vi.hoisted` state so individual tests can set real closed orders — see
// `mockClosedOrdersState` usage below (`vi.mock` factories are hoisted above
// module-scope `let`/`const`, so a plain outer variable would be undefined).
const { mockClosedOrdersState } = vi.hoisted(() => ({
  mockClosedOrdersState: { orders: [] as ClosedOrder[] },
}));

vi.mock('../closed_orders/useClosedOrders', () => ({
  useClosedOrders: () => ({
    orders: mockClosedOrdersState.orders,
    loading: false,
    refresh: () => {},
  }),
}));

vi.mock('./TraderNovaOsBrain', () => ({
  TraderNovaOsBrain: ({ symbol }: { symbol: string }) => (
    <div data-testid="trader-nova-os-brain">Nova OS mock {symbol}</div>
  ),
}));

const ORDER: IbkrOrder = {
  order_id: 99,
  symbol: 'AAPL',
  side: 'BUY',
  qty: 1,
  filled_qty: 0,
  remaining_qty: 1,
  order_type: 'LMT',
  limit_price: 190,
  stop_price: null,
  avg_fill_price: null,
  outside_rth: false,
  status: 'Submitted',
};

const CLOSED_AAPL: ClosedOrder = {
  order_id: 501,
  symbol: 'AAPL',
  side: 'BUY',
  qty: 50,
  filled_qty: 50,
  remaining_qty: 0,
  order_type: 'MKT',
  limit_price: null,
  stop_price: null,
  avg_fill_price: 190.2,
  outside_rth: false,
  status: 'Filled',
  submitted_at: '2026-07-21T13:00:00.000Z',
  updated_at: '2026-07-21T13:00:05.000Z',
  filled_at: '2026-07-21T13:00:05.000Z',
};

const POSITION: IbkrPosition = {
  symbol: 'AAPL',
  qty: 100,
  market_price: 190,
  market_value: 19000,
  avg_cost: 185,
  unrealized_pnl: 500,
  realized_pnl: 0,
};

const baseProps = {
  symbol: 'AAPL',
  orders: [] as IbkrOrder[],
  positions: [] as IbkrPosition[],
  summary: null,
  mode: 'paper' as const,
  connected: true,
  onSelectSymbol: () => {},
};

describe('StockViewOpenOrdersDock', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    mockClosedOrdersState.orders = [];
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('auto-shows sample rows when empty and expands', () => {
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    const dock = container.querySelector(
      '[data-testid="stock-view-open-orders-dock"]',
    );
    expect(dock).toBeTruthy();
    expect(dock?.getAttribute('data-sample')).toBe('1');
    expect(container.textContent).toContain(ORDERS_TODAY_TITLE);
    expect(
      container.querySelector('[data-testid="orders-today-filters"]'),
    ).toBeTruthy();
    expect(container.textContent).toContain('90001');
    expect(localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY)).toBe('0');
  });

  it('Orders badge counts real closed orders for a pre-existing position with no working order', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    mockClosedOrdersState.orders = [CLOSED_AAPL];
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    const ordersTab = container.querySelector(
      '[data-testid="stock-view-dock-tab-orders"]',
    );
    expect(ordersTab?.querySelector('.sv-open-orders-dock__count')?.textContent).toBe(
      '1',
    );
  });

  it('auto-expands when highlightOrderId is set after place', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, '1');
    act(() => {
      root.render(
        <StockViewOpenOrdersDock
          {...baseProps}
          orders={[ORDER]}
          highlightOrderId={99}
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="working-orders-panel"]'),
    ).toBeTruthy();
    expect(container.textContent).toContain('99');
  });

  it('toggles when clicking the middle of the bar (hint area)', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, '1');
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    expect(
      container.querySelector('[data-testid="orders-today-view"]'),
    ).toBeNull();
    const hint = container.querySelector('.sv-open-orders-dock__hint');
    act(() => {
      hint?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(
      container.querySelector('[data-testid="orders-today-view"]'),
    ).toBeTruthy();
  });

  it('switches to Positions table and shows open positions', () => {
    act(() => {
      root.render(
        <StockViewOpenOrdersDock {...baseProps} positions={[POSITION]} />,
      );
    });
    const tab = container.querySelector(
      '[data-testid="stock-view-dock-tab-positions"]',
    ) as HTMLButtonElement;
    expect(tab).toBeTruthy();
    expect(container.textContent).toContain(STOCK_VIEW_MODULE_POSITIONS_TITLE);
    act(() => {
      tab.click();
    });
    expect(
      container.querySelector('[data-testid="stock-view-positions"]'),
    ).toBeTruthy();
    expect(container.querySelector('[data-testid="positions-table"]')).toBeTruthy();
    expect(container.textContent).toContain('AAPL');
    expect(container.textContent).toContain('100');
    expect(
      container
        .querySelector('[data-testid="stock-view-open-orders-dock"]')
        ?.getAttribute('data-dock-surface'),
    ).toBe('positions');
  });

  it('switches to Nova OS tab and mounts the judgment panel', () => {
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    const tab = container.querySelector(
      '[data-testid="stock-view-dock-tab-nova-os"]',
    ) as HTMLButtonElement;
    expect(tab).toBeTruthy();
    expect(container.textContent).toContain(STOCK_VIEW_MODULE_NOVA_OS_TITLE);
    act(() => {
      tab.click();
    });
    expect(
      container.querySelector('[data-testid="stock-view-nova-os"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('[data-testid="trader-nova-os-brain"]'),
    ).toBeTruthy();
    expect(
      container
        .querySelector('[data-testid="stock-view-open-orders-dock"]')
        ?.getAttribute('data-dock-surface'),
    ).toBe('nova_os');
  });
});
