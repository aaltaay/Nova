/**
 * @vitest-environment jsdom
 *
 * MASTER TEST QTY GATE (#444): the door caps every Live order at `qty_cap`
 * shares; Paper and Sim are not capped and report `qty_cap: null`. The ticket
 * must say the sent size whenever the typed size is above the cap, and stay
 * quiet when it is not -- or when there is no cap.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderTicket } from './ManualOrderTicket';

const status = vi.hoisted(() => ({
  current: {
    connected: true,
    mode: 'live',
    spend_status: 'live_armed',
    trading_allowed: true,
    trading_allowed_reason: null,
    qty_cap: 1 as number | null,
  },
}));

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  tryUnlockTicketSession: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));

vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => status.current,
}));

describe('ManualOrderTicket quantity cap note', () => {
  let container: HTMLDivElement;
  let root: Root;

  function renderTicket(mode: 'live' | 'paper', qtyCap: number | null) {
    status.current = {
      ...status.current,
      mode,
      spend_status: `${mode}_armed`,
      qty_cap: qtyCap,
    };
    localStorage.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="CCL"
          mode={mode}
          connected
          spendStatus={`${mode}_armed`}
          summary={{ connected: true, mode, NetLiquidation: 25000, BuyingPower: 25000 }}
          position={null}
          referencePrice={22}
        />,
      );
    });
  }

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

  const note = () => container.querySelector('[data-testid="qty-cap-note"]');

  it('says the sent size on Live when the typed size is above the cap', () => {
    renderTicket('live', 1);
    typeQuantity('10');
    expect(note()?.textContent).toBe('Live cap: this order sends 1 of 10 shares.');
  });

  it('stays quiet on Live at the cap', () => {
    renderTicket('live', 1);
    typeQuantity('1');
    expect(note()).toBeNull();
  });

  it('stays quiet on Paper, which is not capped', () => {
    renderTicket('paper', null);
    typeQuantity('100');
    expect(note()).toBeNull();
  });
});
