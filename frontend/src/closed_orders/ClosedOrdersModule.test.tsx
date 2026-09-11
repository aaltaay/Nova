/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CLOSED_ORDERS_EMPTY_MESSAGE } from '../constants';
import { SampleDataProvider } from '../sample_data/SampleDataContext';
import { ClosedOrdersModule } from './ClosedOrdersModule';

vi.mock('../ibkr/useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper' }),
}));

vi.mock('./useClosedOrders', () => ({
  useClosedOrders: () => ({
    orders: [],
    error: null,
    loading: false,
    refresh: () => {},
  }),
}));

describe('ClosedOrdersModule sample default', () => {
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

  it('does not paint mock closed rows when IB returns zero orders', () => {
    act(() => {
      root.render(<ClosedOrdersModule />);
    });
    expect(container.textContent).toContain(CLOSED_ORDERS_EMPTY_MESSAGE);
    expect(container.textContent).not.toContain('9001');
    expect(
      container.querySelector('[data-testid="closed-orders-toggle-sample"]')
        ?.textContent,
    ).toBe('Show sample');
    expect(
      container
        .querySelector('[data-testid="closed-orders-panel"]')
        ?.getAttribute('data-sample'),
    ).not.toBe('1');
  });

  it('Show sample opt-in paints mock closed rows', () => {
    act(() => {
      root.render(<ClosedOrdersModule />);
    });
    const toggle = container.querySelector(
      '[data-testid="closed-orders-toggle-sample"]',
    ) as HTMLButtonElement;
    act(() => {
      toggle.click();
    });
    expect(toggle.textContent).toBe('Hide sample');
    expect(container.textContent).toContain('9001');
    expect(
      container
        .querySelector('[data-testid="closed-orders-panel"]')
        ?.getAttribute('data-sample'),
    ).toBe('1');
  });

  it('defaults to sample rows when SampleDataProvider is active', () => {
    act(() => {
      root.render(
        <SampleDataProvider>
          <ClosedOrdersModule />
        </SampleDataProvider>,
      );
    });
    expect(container.textContent).toContain('9001');
    expect(
      container.querySelector('[data-testid="closed-orders-toggle-sample"]')
        ?.textContent,
    ).toBe('Hide sample');
  });
});
