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
import { defaultTradeDefaultsPrefs, writeTradeDefaultsPrefs } from '../settings/tradeDefaultsPrefs';

const confirmed = vi.hoisted(() => ({ current: { venue: 'paper' as 'paper' | 'live', generation: 'paper-1' } }));
vi.mock('./confirmedDeskVenue', () => ({
  getConfirmedDeskVenueSnapshot: () => confirmed.current,
  subscribeConfirmedDeskVenue: () => () => {},
}));

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
    confirmed.current = { venue: 'paper', generation: 'paper-1' };
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
    if (confirmed.current.venue !== mode) confirmed.current = { venue: mode, generation: `${mode}-1` };
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

  it('invalidates a confirm after Paper to Live to Paper even when mode ends on the same value', () => {
    render('paper');
    act(() => { (container.querySelector('.manual-order-submit') as HTMLButtonElement).click(); });
    expect(confirmOpen()).toBe(true);
    confirmed.current = { venue: 'paper', generation: 'paper-after-live' };
    render('paper');
    expect(confirmOpen()).toBe(false);
  });

  it('reads explicit Live defaults on a legacy Paper Gateway without reading Paper preferences', () => {
    writeTradeDefaultsPrefs('live', { ...defaultTradeDefaultsPrefs(), quantity: 3, tif: 'GTC' });
    writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 7 });
    confirmed.current = { venue: 'live', generation: 'live-legacy-gateway' };
    // The by-hand Gateway mode remains paper; the confirmed source says Live.
    act(() => {
      root.render(<ManualOrderTicket symbol="SPY" mode="paper" connected spendStatus="live_armed" summary={{ connected: true, NetLiquidation: 1000, BuyingPower: 1000 }} position={null} referencePrice={100} />);
    });
    expect((container.querySelector('#manual-order-quantity') as HTMLInputElement).value).toBe('3');
    expect(container.querySelector('[data-testid="manual-order-tif-gtc"]')?.getAttribute('aria-pressed')).toBe('true');
  });
});
