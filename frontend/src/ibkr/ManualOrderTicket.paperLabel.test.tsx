/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  TICKER_TRADE_PLACE_ORDER_LABEL,
  TICKER_TRADE_PLACE_PAPER_ORDER_LABEL,
} from '../constants';
import { ManualOrderTicket } from './ManualOrderTicket';

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  tryUnlockTicketSession: () => true,
}));

describe('ManualOrderTicket paper place label', () => {
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

  it('uses orange Place Paper order CTA in paper mode', () => {
    render('paper');
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe(TICKER_TRADE_PLACE_PAPER_ORDER_LABEL);
    expect(btn.classList.contains('manual-order-submit--paper')).toBe(true);
  });

  it('keeps blue Place an order CTA in live mode', () => {
    render('live');
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe(TICKER_TRADE_PLACE_ORDER_LABEL);
    expect(btn.classList.contains('manual-order-submit--paper')).toBe(false);
  });
});
