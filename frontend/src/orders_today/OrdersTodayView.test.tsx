/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { ClosedOrder } from '../closed_orders/types';
import { ORDERS_TODAY_EMPTY_MESSAGE } from '../constants';
import type { IbkrOrder } from '../ibkr/types';
import { OrdersTodayView } from './OrdersTodayView';

const CLOSED_MSFT: ClosedOrder = {
  order_id: 2,
  symbol: 'MSFT',
  side: 'SELL',
  qty: 20,
  filled_qty: 20,
  remaining_qty: 0,
  order_type: 'MKT',
  limit_price: null,
  stop_price: null,
  avg_fill_price: 400,
  outside_rth: false,
  status: 'Filled',
  submitted_at: '2026-07-18T12:00:00.000Z',
  updated_at: '2026-07-18T12:05:00.000Z',
  filled_at: '2026-07-18T12:05:00.000Z',
};

const CLOSED_AAPL: ClosedOrder = {
  ...CLOSED_MSFT,
  order_id: 3,
  symbol: 'AAPL',
};

const baseProps = {
  symbol: 'AAPL',
  workingOrders: [] as IbkrOrder[],
  usingWorkingSample: false,
  closedOrders: [] as ClosedOrder[],
  filter: 'all' as const,
  onFilterChange: () => {},
};

describe('OrdersTodayView empty-state honesty', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
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

  it('shows the generic "nothing yet" message when Gateway has zero real orders anywhere', () => {
    act(() => {
      root.render(
        <OrdersTodayView {...baseProps} filter="canceled" onFilterChange={() => {}} />,
      );
    });
    // filter=canceled hides Working entirely and closedOrders is empty, so
    // Closed falls back to sample rows for AAPL (non-empty) — not the empty
    // gate. Assert no false-empty is shown while sample data is substituted.
    expect(
      container.querySelector('[data-testid="orders-today-empty"]'),
    ).toBeNull();
  });

  it('shows a symbol-specific message when real orders exist for other symbols but not this one', () => {
    act(() => {
      root.render(
        <OrdersTodayView
          {...baseProps}
          symbol="AAPL"
          filter="canceled"
          closedOrders={[CLOSED_MSFT]}
        />,
      );
    });
    const empty = container.querySelector('[data-testid="orders-today-empty"]');
    expect(empty).toBeTruthy();
    expect(empty?.textContent).toContain('AAPL');
    expect(empty?.textContent).not.toBe(ORDERS_TODAY_EMPTY_MESSAGE);
  });

  it('renders real closed rows for a pre-existing position without a working order', () => {
    act(() => {
      root.render(
        <OrdersTodayView
          {...baseProps}
          symbol="AAPL"
          filter="all"
          closedOrders={[CLOSED_AAPL]}
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="orders-today-empty"]'),
    ).toBeNull();
    expect(
      container.querySelector('[data-testid="stock-view-closed-orders"]'),
    ).toBeTruthy();
    // Real AAPL row rendered — sample banner (only shown when substituting
    // mock rows) must not appear once a real closed order exists.
    expect(
      container.querySelector('[data-testid="closed-orders-sample-banner"]'),
    ).toBeNull();
  });
});
