/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderTicket } from './OrderTicket';

vi.mock('./ManualOrderTicket', () => ({
  ManualOrderTicket: () => <div data-testid="manual-order-ticket-stub">Manual ticket</div>,
}));

describe('OrderTicket', () => {
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

  it('has no Automate or Coming soon affordance', () => {
    act(() => {
      root.render(
        <OrderTicket
          defaultSymbol="AAPL"
          mode="disconnected"
          connected={false}
          summary={null}
          positions={[]}
        />,
      );
    });
    expect(container.textContent).toContain('Order Ticket');
    expect(container.querySelector('[data-testid="manual-order-ticket-stub"]')).toBeTruthy();
    expect(container.querySelector('.ibkr-automate-btn')).toBeNull();
    expect(container.textContent).not.toMatch(/Automate/i);
    expect(container.textContent).not.toMatch(/coming soon/i);
  });
});
