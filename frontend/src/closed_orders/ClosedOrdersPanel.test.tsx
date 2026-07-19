/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { CLOSED_ORDERS_PANEL_TITLE } from '../constants';
import { ClosedOrdersPanel } from './ClosedOrdersPanel';
import type { ClosedOrder } from './types';

const SAMPLE: ClosedOrder[] = [
  {
    order_id: 10,
    symbol: 'AAPL',
    side: 'BUY',
    qty: 100,
    filled_qty: 100,
    remaining_qty: 0,
    order_type: 'LMT',
    limit_price: 190,
    avg_fill_price: 189.9,
    outside_rth: false,
    status: 'Filled',
  },
  {
    order_id: 11,
    symbol: 'MSFT',
    side: 'SELL',
    qty: 20,
    filled_qty: 0,
    remaining_qty: 0,
    order_type: 'MKT',
    limit_price: null,
    avg_fill_price: null,
    outside_rth: false,
    status: 'Cancelled',
  },
];

describe('ClosedOrdersPanel', () => {
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

  it('renders filled/cancelled with Webull-clean labels and no Cancel action', () => {
    act(() => {
      root.render(<ClosedOrdersPanel orders={SAMPLE} />);
    });
    expect(container.querySelector('[data-testid="closed-orders-panel"]')).toBeTruthy();
    expect(container.textContent).toContain(CLOSED_ORDERS_PANEL_TITLE);
    expect(container.textContent).toContain('Filled');
    expect(container.textContent).toContain('Cancelled');
    expect(container.textContent).toContain('Limit Order');
    expect(container.textContent).not.toMatch(/\bLMT\b/);
    expect(container.querySelector('[aria-label^="Cancel order"]')).toBeNull();
    expect(container.textContent).toMatch(/Working Orders/);
  });

  it('filters to Filled tab only', () => {
    act(() => {
      root.render(<ClosedOrdersPanel orders={SAMPLE} />);
    });
    const filledTab = container.querySelector('[data-filter="filled"]') as HTMLButtonElement;
    act(() => {
      filledTab.click();
    });
    expect(container.textContent).toContain('AAPL');
    expect(container.textContent).not.toContain('MSFT');
  });
});
