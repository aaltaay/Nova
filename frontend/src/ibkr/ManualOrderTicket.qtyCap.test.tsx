/**
 * @vitest-environment jsdom
 *
 * MASTER TEST QTY GATE (#444): the door caps every order at `qty_cap` shares.
 * The ticket must say the sent size whenever the typed size is above the cap,
 * and stay quiet when it is not.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderTicket } from './ManualOrderTicket';

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  tryUnlockTicketSession: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));

vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
    trading_allowed: true,
    trading_allowed_reason: null,
    qty_cap: 10,
  }),
}));

describe('ManualOrderTicket test quantity cap note', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="CCL"
          mode="paper"
          connected
          spendStatus="paper_armed"
          summary={{ connected: true, mode: 'paper', NetLiquidation: 25000, BuyingPower: 25000 }}
          position={null}
          referencePrice={22}
        />,
      );
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function typeQuantity(value: string) {
    const input = container.querySelector('#manual-order-quantity') as HTMLInputElement;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    act(() => {
      setter?.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  it('says the sent size when the typed size is above the cap', () => {
    typeQuantity('100');
    const note = container.querySelector('[data-testid="qty-cap-note"]');
    expect(note?.textContent).toBe('Test cap: this order sends 10 of 100 shares.');
  });

  it('stays quiet at or under the cap', () => {
    typeQuantity('10');
    expect(container.querySelector('[data-testid="qty-cap-note"]')).toBeNull();
    typeQuantity('5');
    expect(container.querySelector('[data-testid="qty-cap-note"]')).toBeNull();
  });
});
