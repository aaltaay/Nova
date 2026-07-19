/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { WorkingOrdersPanel } from './WorkingOrdersPanel';
import type { IbkrOrder } from './types';
import { WORKING_ORDERS_PANEL_TITLE } from '../constants';

const SAMPLE: IbkrOrder[] = [
  {
    order_id: 42,
    symbol: 'AAPL',
    side: 'BUY',
    qty: 100,
    filled_qty: 25,
    remaining_qty: 75,
    order_type: 'LMT',
    limit_price: 190.5,
    stop_price: null,
    avg_fill_price: 190.4,
    outside_rth: false,
    status: 'Submitted',
  },
  {
    order_id: 43,
    symbol: 'MSFT',
    side: 'SELL',
    qty: 50,
    filled_qty: 0,
    remaining_qty: 50,
    order_type: 'MKT',
    limit_price: null,
    stop_price: null,
    avg_fill_price: null,
    outside_rth: true,
    status: 'PreSubmitted',
  },
];

describe('WorkingOrdersPanel', () => {
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

  it('renders Webull-clean labels (no IBKR abbreviations)', () => {
    act(() => {
      root.render(<WorkingOrdersPanel orders={SAMPLE} />);
    });
    expect(container.querySelector('[data-testid="working-orders-panel"]')).toBeTruthy();
    expect(container.textContent).toContain(WORKING_ORDERS_PANEL_TITLE);
    expect(container.textContent).toContain('AAPL');
    expect(container.textContent).toContain('Limit Order');
    expect(container.textContent).toContain('Market Order');
    expect(container.textContent).toContain('Partially filled');
    expect(container.textContent).toContain('Pending');
    // Side is color-coded on symbol/qty — no Buy/Sell text column.
    expect(container.textContent).not.toMatch(/\bBuy\b/);
    expect(container.textContent).not.toMatch(/\bSell\b/);
    expect(
      container.querySelector('td.ibkr-symbol[data-side="BUY"]')?.className,
    ).toMatch(/ibkr-side--buy/);
    expect(container.querySelector('tr.ibkr-order-row--buy')).toBeTruthy();
    expect(container.querySelector('tr.ibkr-order-row--sell')).toBeTruthy();
    expect(container.textContent).not.toContain('PreSubmitted');
    expect(container.textContent).not.toMatch(/\bLMT\b/);
    expect(container.textContent).toContain('25');
    expect(container.textContent).toContain('$190.40');
  });

  it('filters by symbol and hides title when compact', () => {
    act(() => {
      root.render(
        <WorkingOrdersPanel
          orders={SAMPLE}
          filterSymbol="aapl"
          hideTitle
          compact
        />,
      );
    });
    expect(container.textContent).not.toContain(WORKING_ORDERS_PANEL_TITLE);
    expect(container.textContent).toContain('AAPL');
    expect(container.textContent).not.toContain('MSFT');
  });

  it('highlights a just-placed order id', () => {
    act(() => {
      root.render(<WorkingOrdersPanel orders={SAMPLE} highlightOrderId={42} />);
    });
    expect(container.querySelector('.ibkr-order-row--highlight')).toBeTruthy();
    expect(
      container
        .querySelector('[data-testid="working-orders-panel"]')
        ?.getAttribute('data-highlight-order'),
    ).toBe('42');
  });

  it('invokes cancel without placing orders', () => {
    const onCancel = vi.fn();
    act(() => {
      root.render(<WorkingOrdersPanel orders={SAMPLE} onCancelOrder={onCancel} />);
    });
    const btn = container.querySelector(
      '[aria-label="Cancel order 42"]',
    ) as HTMLButtonElement;
    expect(btn).toBeTruthy();
    act(() => {
      btn.click();
    });
    expect(onCancel).toHaveBeenCalledWith(42);
  });

  it('invokes Fill now with the order row', () => {
    const onFill = vi.fn();
    act(() => {
      root.render(
        <WorkingOrdersPanel orders={SAMPLE} onFillImmediately={onFill} />,
      );
    });
    const btn = container.querySelector(
      '[aria-label="Fill now order 42"]',
    ) as HTMLButtonElement;
    expect(btn).toBeTruthy();
    act(() => {
      btn.click();
    });
    expect(onFill).toHaveBeenCalledWith(
      expect.objectContaining({ order_id: 42, remaining_qty: 75 }),
    );
  });
});

