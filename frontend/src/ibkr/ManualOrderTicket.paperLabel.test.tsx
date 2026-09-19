/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderTicket } from './ManualOrderTicket';
import { placeActionLabel } from './ticketSide';

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
  }),
}));

describe('ManualOrderTicket paper place label', () => {
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

  it('uses orange Buy SYMBOL CTA in paper mode', () => {
    render('paper');
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe(placeActionLabel('buy', 'SPY'));
    expect(btn.classList.contains('manual-order-submit--paper')).toBe(true);
  });

  it('keeps blue Buy SYMBOL CTA in live mode', () => {
    render('live');
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toBe(placeActionLabel('buy', 'SPY'));
    expect(btn.classList.contains('manual-order-submit--paper')).toBe(false);
  });

  it('shows an enabled Extended Hours checkbox on Market (default)', () => {
    localStorage.clear();
    render('live');
    const box = container.querySelector(
      '[data-testid="manual-order-extended"]',
    ) as HTMLInputElement;
    expect(box).toBeTruthy();
    expect(box.checked).toBe(true);
    expect(box.disabled).toBe(false);
    expect(container.querySelector('#manual-order-hours')).toBeNull();
  });
});
