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
    submitted_at: '2026-07-18T12:00:00.000Z',
    updated_at: '2026-07-18T12:05:00.000Z',
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
    submitted_at: '2026-07-18T12:10:00.000Z',
    updated_at: '2026-07-18T12:11:00.000Z',
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

  it('highlights rows completed within the last minute', () => {
    const recentIso = new Date().toISOString();
    const withRecent: ClosedOrder[] = [
      ...SAMPLE,
      {
        order_id: 12,
        symbol: 'NVDA',
        side: 'BUY',
        qty: 10,
        filled_qty: 10,
        remaining_qty: 0,
        order_type: 'MKT',
        limit_price: null,
        avg_fill_price: 100,
        outside_rth: false,
        status: 'Filled',
        submitted_at: recentIso,
        updated_at: recentIso,
      },
    ];
    act(() => {
      root.render(<ClosedOrdersPanel orders={withRecent} />);
    });
    const recentRows = container.querySelectorAll('tr[data-recent="1"]');
    expect(recentRows.length).toBe(1);
    expect(recentRows[0].className).toMatch(/ibkr-order-row--recent/);
    expect(container.querySelectorAll('tr[data-side]').length).toBe(3);
  });

  it('shows an error line instead of the empty message when the poll failed', () => {
    act(() => {
      root.render(<ClosedOrdersPanel orders={[]} error="closed orders unavailable (HTTP 503)" />);
    });
    expect(container.textContent).toContain('closed orders unavailable');
    expect(container.querySelector('[data-testid="closed-orders-error"]')).toBeTruthy();
  });

  it('keeps last-good rows visible alongside the error banner', () => {
    act(() => {
      root.render(<ClosedOrdersPanel orders={SAMPLE} error="closed orders unavailable (HTTP 503)" />);
    });
    expect(container.textContent).toContain('closed orders unavailable');
    expect(container.textContent).toContain('AAPL');
  });
});
