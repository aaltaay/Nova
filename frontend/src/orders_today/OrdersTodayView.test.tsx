/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { ClosedOrder } from '../closed_orders/types';
import {
  ORDERS_TODAY_EMPTY_FILTER_MESSAGE,
  ORDERS_TODAY_EMPTY_MESSAGE,
} from '../constants';
import type { IbkrOrder } from '../ibkr/types';
import { SampleDataProvider } from '../sample_data/SampleDataContext';
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

describe('OrdersTodayView account-wide', () => {
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
    const empty = container.querySelector('[data-testid="orders-today-empty"]');
    expect(empty).toBeTruthy();
    expect(empty?.textContent).toBe(ORDERS_TODAY_EMPTY_MESSAGE);
    expect(
      container.querySelector('[data-testid="orders-today-closed-sample-toggle"]')
        ?.textContent,
    ).toBe('Show closed sample');
  });

  it('Show closed sample opt-in paints mock closed rows', () => {
    act(() => {
      root.render(
        <OrdersTodayView {...baseProps} filter="canceled" onFilterChange={() => {}} />,
      );
    });
    const toggle = container.querySelector(
      '[data-testid="orders-today-closed-sample-toggle"]',
    ) as HTMLButtonElement;
    act(() => {
      toggle.click();
    });
    expect(
      container.querySelector('[data-testid="orders-today-empty"]'),
    ).toBeNull();
    expect(container.textContent).toContain('9003');
  });

  it('defaults to closed sample rows under SampleDataProvider', () => {
    act(() => {
      root.render(
        <SampleDataProvider>
          <OrdersTodayView
            {...baseProps}
            filter="canceled"
            onFilterChange={() => {}}
          />
        </SampleDataProvider>,
      );
    });
    expect(
      container.querySelector('[data-testid="orders-today-empty"]'),
    ).toBeNull();
    expect(container.textContent).toContain('9003');
  });

  it('shows other-symbol closed fills while Stock View is on a different ticker', () => {
    act(() => {
      root.render(
        <OrdersTodayView
          {...baseProps}
          symbol="AAPL"
          filter="all"
          closedOrders={[CLOSED_MSFT]}
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="orders-today-empty"]'),
    ).toBeNull();
    expect(
      container.querySelector('[data-testid="stock-view-closed-orders"]'),
    ).toBeTruthy();
    expect(container.textContent).toMatch(/MSFT/);
  });

  it('uses account filter empty copy when real orders exist but segment is empty', () => {
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
    // Real closed fills exist (so no sample substitute); canceled segment is empty.
    const empty = container.querySelector('[data-testid="orders-today-empty"]');
    expect(empty).toBeTruthy();
    expect(empty?.textContent).toBe(ORDERS_TODAY_EMPTY_FILTER_MESSAGE);
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
    expect(
      container.querySelector('[data-testid="closed-orders-sample-banner"]'),
    ).toBeNull();
  });
});
