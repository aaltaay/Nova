/**
 * @vitest-environment jsdom
 *
 * Right-click a working order and cancel it (operator ask 2026-10-14).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { WORKING_ORDER_READ_FAILED_WHY } from '../constants';
import type { IbkrOrder } from './types';
import { WorkingOrdersPanel } from './WorkingOrdersPanel';
import { workingOrderCancelHint, workingOrderMenuPosition, workingOrderSummary } from './WorkingOrderMenu';

const GLND: IbkrOrder = {
  order_id: 247,
  perm_id: 247,
  venue: 'paper',
  symbol: 'GLND',
  side: 'BUY',
  qty: 1000,
  filled_qty: 0,
  remaining_qty: 1000,
  order_type: 'LMT',
  limit_price: 4,
  stop_price: null,
  avg_fill_price: null,
  outside_rth: true,
  status: 'Submitted',
  submitted_at: '2026-10-14T11:54:34.207Z',
  updated_at: '2026-10-14T11:54:34.207Z',
};

const menu = () => document.querySelector<HTMLElement>('[data-testid="working-order-menu"]');
const cancelRow = () => document.querySelector<HTMLButtonElement>('[data-testid="working-order-menu-cancel"]');

describe('the working order right-click menu', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const rightClick = (row: Element, x = 200, y = 300) => {
    const event = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: x, clientY: y });
    act(() => {
      row.dispatchEvent(event);
    });
    return event;
  };

  it('names the order and cancels it in one click, then closes', () => {
    const onCancelOrder = vi.fn();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} />));
    const row = container.querySelector('tr[data-order-id="247"]')!;
    const event = rightClick(row);
    expect(event.defaultPrevented).toBe(true);
    expect(menu()?.textContent).toContain('GLND');
    expect(document.querySelector('[data-testid="working-order-menu-order"]')?.textContent).toBe('Buy 1,000 at $4.00');
    expect(row.className).toContain('ibkr-order-row--menu');
    act(() => cancelRow()!.click());
    expect(onCancelOrder).toHaveBeenCalledWith(247);
    expect(menu()).toBeNull();
    expect(row.className).not.toContain('ibkr-order-row--menu');
  });

  it('opens on rows that also open the Trader (Trading tab, Account page)', () => {
    const onCancelOrder = vi.fn();
    act(() => root.render(
      <WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} onSelectSymbol={vi.fn()} onOpenTrading={vi.fn()} />,
    ));
    rightClick(container.querySelector('tbody tr')!);
    act(() => cancelRow()!.click());
    expect(onCancelOrder).toHaveBeenCalledWith(247);
  });

  it('leaves the right-click alone where the table cannot cancel', () => {
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} />));
    const event = rightClick(container.querySelector('tr[data-order-id="247"]')!);
    expect(event.defaultPrevented).toBe(false);
    expect(menu()).toBeNull();
  });

  it('locks Cancel on last-known rows and says why', () => {
    const onCancelOrder = vi.fn();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} error="poll failed" />));
    rightClick(container.querySelector('tr[data-order-id="247"]')!);
    expect(cancelRow()!.disabled).toBe(true);
    expect(cancelRow()!.dataset.why).toBe(WORKING_ORDER_READ_FAILED_WHY);
  });

  it('closes when its order fills while it is open, so it never cancels a filled order', () => {
    const onCancelOrder = vi.fn();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} />));
    rightClick(container.querySelector('tr[data-order-id="247"]')!);
    expect(menu()).not.toBeNull();
    act(() => root.render(<WorkingOrdersPanel orders={[]} onCancelOrder={onCancelOrder} />));
    expect(menu()).toBeNull();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} />));
    expect(menu()).toBeNull();
  });

  it('shows the order as it is now while open', () => {
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={vi.fn()} />));
    rightClick(container.querySelector('tr[data-order-id="247"]')!);
    const partial = { ...GLND, filled_qty: 600, remaining_qty: 400 };
    act(() => root.render(<WorkingOrdersPanel orders={[partial]} onCancelOrder={vi.fn()} />));
    expect(cancelRow()!.textContent).toContain('Cancels the 400 shares still working; the 600 filled stay.');
  });

  it('closes on Escape and on a click elsewhere, without cancelling', () => {
    const onCancelOrder = vi.fn();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND]} onCancelOrder={onCancelOrder} />));
    const row = container.querySelector('tr[data-order-id="247"]')!;
    rightClick(row);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(menu()).toBeNull();
    rightClick(row);
    act(() => {
      document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    expect(menu()).toBeNull();
    expect(onCancelOrder).not.toHaveBeenCalled();
  });

  it('a second right-click on another order moves the menu to it', () => {
    const other = { ...GLND, order_id: 248, perm_id: 248, limit_price: 4.1 };
    const onCancelOrder = vi.fn();
    act(() => root.render(<WorkingOrdersPanel orders={[GLND, other]} onCancelOrder={onCancelOrder} />));
    rightClick(container.querySelector('tr[data-order-id="247"]')!);
    rightClick(container.querySelector('tr[data-order-id="248"]')!);
    expect(document.querySelectorAll('[data-testid="working-order-menu"]')).toHaveLength(1);
    act(() => cancelRow()!.click());
    expect(onCancelOrder).toHaveBeenCalledWith(248);
  });
});

describe('what the menu says and where it opens', () => {
  it('words each order type the way it was placed', () => {
    expect(workingOrderSummary(GLND)).toBe('Buy 1,000 at $4.00');
    expect(workingOrderSummary({ ...GLND, side: 'SELL', qty: 500, order_type: 'STP', limit_price: null, stop_price: 3.8 }))
      .toBe('Sell 500, stop $3.80');
    expect(workingOrderSummary({ ...GLND, order_type: 'STP LMT', limit_price: 3.75, stop_price: 3.8 }))
      .toBe('Buy 1,000, stop $3.80, limit $3.75');
    expect(workingOrderSummary({ ...GLND, order_type: 'MKT', limit_price: null })).toBe('Buy 1,000 at market');
    expect(workingOrderSummary({ ...GLND, limit_price: 0.4512 })).toBe('Buy 1,000 at $0.4512');
  });

  it('says what a cancel takes away', () => {
    expect(workingOrderCancelHint(GLND)).toBe('Cancels all 1,000 shares. Sends at once. Shares already filled stay.');
  });

  it('opens upward from a click low on the screen and stays inside it', () => {
    expect(workingOrderMenuPosition({ x: 100, y: 200, viewportWidth: 1400, viewportHeight: 900, menuHeight: 120 }))
      .toEqual({ top: 200, left: 100 });
    expect(workingOrderMenuPosition({ x: 100, y: 850, viewportWidth: 1400, viewportHeight: 900, menuHeight: 120 }))
      .toEqual({ top: 730, left: 100 });
    expect(workingOrderMenuPosition({ x: 1390, y: 200, viewportWidth: 1400, viewportHeight: 900, menuHeight: 120 }).left)
      .toBe(1400 - 272 - 4);
  });
});
