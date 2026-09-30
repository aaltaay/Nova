/**
 * @vitest-environment jsdom
 *
 * A confirm built on Paper is never sent on Live (audit 2026-09-30): the venue
 * pill changes the ticket's mode, and the open confirm -- which names the Paper
 * account -- closes instead of waiting to place on Live after a re-arm.
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderTicket } from './ManualOrderTicket';

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));

vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
    trading_allowed: true,
    trading_allowed_reason: null,
  }),
}));

describe('ManualOrderTicket venue switch', () => {
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

  function render(mode: 'paper' | 'live') {
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="SPY"
          mode={mode}
          connected
          spendStatus={mode === 'paper' ? 'paper_armed' : 'live_armed'}
          summary={{ connected: true, mode, NetLiquidation: 1000, BuyingPower: 1000 }}
          position={null}
          referencePrice={100}
        />,
      );
    });
  }

  const confirmOpen = () => /PAPER account/.test(document.body.textContent ?? '');

  it('closes a Paper confirm when the desk moves to Live', () => {
    render('paper');
    const place = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    act(() => {
      place.click();
    });
    expect(confirmOpen()).toBe(true);
    render('live');
    expect(confirmOpen()).toBe(false);
  });
});
