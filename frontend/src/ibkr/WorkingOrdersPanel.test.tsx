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
    submitted_at: '2026-07-18T13:41:23.000Z',
    updated_at: '2026-07-18T18:00:00.000Z',
  },
  {
    order_id: 43,
    symbol: 'MSFT',
    side: 'SELL',
    qty: 50,
    filled_qty: 0,
    remaining_qty: 50,
    order_type: 'STP',
    limit_price: null,
    stop_price: 180.25,
    avg_fill_price: null,
    outside_rth: true,
    status: 'PreSubmitted',
    submitted_at: '2026-07-18T14:00:00.000Z',
    updated_at: '2026-07-18T14:00:00.000Z',
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
    expect(container.textContent).toContain('Stop Order');
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

  it('shows filled, remaining, limit, stop, avg fill, order id, fixed submitted time', () => {
    act(() => {
      root.render(<WorkingOrdersPanel orders={SAMPLE} />);
    });
    const text = container.textContent ?? '';
    // Partial row
    expect(text).toContain('25'); // filled
    expect(text).toContain('75'); // remaining
    expect(text).toContain('$190.50'); // limit
    expect(text).toContain('$190.40'); // avg fill
    expect(text).toContain('42'); // order id
    // Stop row
    expect(text).toContain('$180.25');
    expect(text).toContain('43');
    // Time = submitted snapshot (09:41:23 ET), not updated_at (14:00 ET)
    expect(text).toMatch(/09:41:23/);
    expect(text).not.toMatch(/14:00:00/);
    const timeEl = container.querySelector('time');
    expect(timeEl?.getAttribute('dateTime')).toBe('2026-07-18T13:41:23.000Z');
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

  it('shows an error line instead of "No open orders" when the poll failed', () => {
    act(() => {
      root.render(<WorkingOrdersPanel orders={[]} error="IBKR read failed — orders (HTTP 503)" />);
    });
    expect(container.textContent).toContain('IBKR read failed');
    expect(container.textContent).not.toContain('No open orders.');
  });

  it('keeps showing last-good rows alongside the error banner', () => {
    act(() => {
      root.render(<WorkingOrdersPanel orders={SAMPLE} error="IBKR read failed — orders (HTTP 503)" />);
    });
    expect(container.textContent).toContain('IBKR read failed');
    expect(container.textContent).toContain('AAPL');
  });
});

