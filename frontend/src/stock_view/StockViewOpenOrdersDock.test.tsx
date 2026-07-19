/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY,
} from '../constants';
import { StockViewOpenOrdersDock } from './StockViewOpenOrdersDock';
import type { IbkrOrder } from '../ibkr/types';

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

describe('StockViewOpenOrdersDock', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
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

  it('starts collapsed by default and toggles open', () => {
    act(() => {
      root.render(
        <StockViewOpenOrdersDock symbol="AAPL" orders={[]} />,
      );
    });
    expect(
      container.querySelector('[data-testid="stock-view-open-orders-dock"]'),
    ).toBeTruthy();
    expect(
      container.querySelector('[data-testid="working-orders-panel"]'),
    ).toBeNull();

    const toggle = container.querySelector(
      '[data-testid="stock-view-open-orders-toggle"]',
    ) as HTMLButtonElement;
    act(() => {
      toggle.click();
    });
    expect(
      container.querySelector('[data-testid="working-orders-panel"]'),
    ).toBeTruthy();
    expect(localStorage.getItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY)).toBe('0');
  });

  it('auto-expands when highlightOrderId is set after place', () => {
    localStorage.setItem(STOCK_VIEW_OPEN_ORDERS_COLLAPSED_KEY, '1');
    act(() => {
      root.render(
        <StockViewOpenOrdersDock
          symbol="AAPL"
          orders={[ORDER]}
          highlightOrderId={99}
        />,
      );
    });
    expect(
      container.querySelector('[data-testid="working-orders-panel"]'),
    ).toBeTruthy();
    expect(container.textContent).toMatch(/Open Orders/i);
    expect(container.textContent).toContain('99');
  });
});
