/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  STOCK_VIEW_MODULE_NOVA_OS_TITLE,
  STOCK_VIEW_MODULE_POSITIONS_TITLE,
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
  STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY,
} from '../constants';
import {
  DRAWER_LIVE_NOTE,
  DRAWER_NO_POSITION,
  DRAWER_PAPER_NOTE,
  DRAWER_TAB_ORDERS,
} from '../constantGroups/trader_chrome';
import type { ClosedOrder } from '../closed_orders/types';
import type { IbkrOrder, IbkrPosition } from '../ibkr/types';
import { SampleDataProvider } from '../sample_data/SampleDataContext';
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
  host: 'trader' as const,
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

  it('does not auto-show sample rows when IB returns zero working orders', () => {
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    const dock = container.querySelector(
      '[data-testid="stock-view-open-orders-dock"]',
    );
    expect(dock).toBeTruthy();
    expect(dock?.getAttribute('data-dock-host')).toBe('trader');
    expect(dock?.getAttribute('data-dock-symbol')).toBe('AAPL');
    expect(dock?.getAttribute('data-sample')).not.toBe('1');
    expect(container.textContent).toContain(DRAWER_TAB_ORDERS);
    expect(container.textContent).not.toContain('90001');
    expect(
      container.querySelector('[data-testid="stock-view-open-orders-show-sample"]')
        ?.textContent,
    ).toBe('Show sample');
  });

  it('Show sample opt-in paints mock working rows', () => {
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    const show = container.querySelector(
      '[data-testid="stock-view-open-orders-show-sample"]',
    ) as HTMLButtonElement;
    act(() => {
      show.click();
    });
    const dock = container.querySelector(
      '[data-testid="stock-view-open-orders-dock"]',
    );
    expect(dock?.getAttribute('data-sample')).toBe('1');
    expect(container.textContent).toContain('90001');
    expect(
      container.querySelector('[data-testid="orders-today-filters"]'),
    ).toBeTruthy();
    expect(
      JSON.parse(localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY) ?? '').value,
    ).toBe(false);
  });

  it('auto-shows sample rows under SampleDataProvider', () => {
    act(() => {
      root.render(
        <SampleDataProvider>
          <StockViewOpenOrdersDock {...baseProps} />
        </SampleDataProvider>,
      );
    });
    const dock = container.querySelector(
      '[data-testid="stock-view-open-orders-dock"]',
    );
    expect(dock?.getAttribute('data-sample')).toBe('1');
    expect(container.textContent).toContain('90001');
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

  it('toggles when clicking bare bar space, and from the chevron at the right', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, '1');
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} />);
    });
    expect(
      container.querySelector('[data-testid="orders-today-view"]'),
    ).toBeNull();
    const bar = container.querySelector('.sv-open-orders-dock__bar');
    act(() => {
      bar?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });
    expect(
      container.querySelector('[data-testid="orders-today-view"]'),
    ).toBeTruthy();
    const chevron = container.querySelector(
      '[data-testid="stock-view-open-orders-toggle"]',
    ) as HTMLButtonElement;
    expect(chevron.getAttribute('aria-expanded')).toBe('true');
    act(() => {
      chevron.click();
    });
    expect(
      container.querySelector('[data-testid="orders-today-view"]'),
    ).toBeNull();
    expect(chevron.getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('[data-testid="stock-view-dock-footer"]')).toBeNull();
  });

  it('keeps the status chips on the tab row with their counts, and no second copy in the body', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_SAMPLE_HIDDEN_KEY, '1');
    mockClosedOrdersState.orders = [CLOSED_AAPL];
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} orders={[ORDER]} />);
    });
    const bar = container.querySelector('.sv-open-orders-dock__bar')!;
    expect(bar.querySelector('[data-testid="orders-today-filters"]')).toBeTruthy();
    expect(
      container.querySelector('.sv-open-orders-dock__body [data-testid="orders-today-filters"]'),
    ).toBeNull();
    expect(bar.querySelector('[data-testid="orders-today-count-working"]')?.textContent).toBe('1');
    expect(bar.querySelector('[data-testid="orders-today-count-filled"]')?.textContent).toBe('1');
    expect(bar.querySelector('[data-testid="orders-today-count-canceled"]')?.textContent).toBe('0');
    expect(bar.querySelector('[data-testid="orders-today-count-all"]')?.textContent).toBe('2');
    act(() => {
      (bar.querySelector('[data-testid="orders-today-filter-filled"]') as HTMLButtonElement).click();
    });
    expect(
      container
        .querySelector('[data-testid="stock-view-open-orders-dock"]')
        ?.getAttribute('data-orders-filter'),
    ).toBe('filled');
    expect(container.querySelector('[data-testid="stock-view-closed-orders"]')).toBeTruthy();
    // The chips belong to Orders: Positions hides them.
    act(() => {
      (container.querySelector('[data-testid="stock-view-dock-tab-positions"]') as HTMLButtonElement).click();
    });
    expect(bar.querySelector('[data-testid="orders-today-filters"]')).toBeNull();
  });

  it('footer names the open position with the est chip on a practice venue and the venue note', () => {
    act(() => {
      root.render(
        <StockViewOpenOrdersDock
          {...baseProps}
          positions={[POSITION]}
          symbolPosition={POSITION}
        />,
      );
    });
    const foot = container.querySelector('[data-testid="stock-view-dock-footer"]')!;
    expect(foot.textContent).toContain('Position AAPL +100 @ 185.00');
    expect(foot.querySelector('[data-testid="est-chip"]')).toBeTruthy();
    expect(foot.textContent).toContain('unrealized +$500.00');
    expect(foot.textContent).toContain(DRAWER_PAPER_NOTE);
  });

  it('footer states a flat symbol and drops the est chip on Live', () => {
    act(() => {
      root.render(
        <StockViewOpenOrdersDock
          {...baseProps}
          mode="live"
          positions={[{ ...POSITION, unrealized_pnl: -12.5 }]}
          symbolPosition={{ ...POSITION, unrealized_pnl: -12.5 }}
        />,
      );
    });
    let foot = container.querySelector('[data-testid="stock-view-dock-footer"]')!;
    expect(foot.querySelector('[data-testid="est-chip"]')).toBeNull();
    expect(foot.textContent).toContain('unrealized −$12.50');
    expect(foot.textContent).toContain(DRAWER_LIVE_NOTE);
    act(() => {
      root.render(<StockViewOpenOrdersDock {...baseProps} mode="live" symbolPosition={null} />);
    });
    foot = container.querySelector('[data-testid="stock-view-dock-footer"]')!;
    expect(foot.textContent).toContain(`${DRAWER_NO_POSITION} · AAPL`);
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

  it('opens Positions when the chart tag requests the dock', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, '1');
    act(() => {
      root.render(
        <StockViewOpenOrdersDock {...baseProps} positions={[POSITION]} />,
      );
    });
    expect(
      container.querySelector('[data-testid="stock-view-positions"]'),
    ).toBeNull();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('nova:stock-view-dock', { detail: { surface: 'positions' } }),
      );
    });
    expect(
      container.querySelector('[data-testid="stock-view-positions"]'),
    ).toBeTruthy();
    expect(container.textContent).toContain('AAPL');
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
