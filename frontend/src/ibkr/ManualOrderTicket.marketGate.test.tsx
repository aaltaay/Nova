/**
 * MKT_OUTSIDE_RTH (operator decision, 2026-09-21): outside regular hours the
 * ticket's Market default moves to Limit and Market greys out with the reason,
 * so the Place that reaches the backend is one it will accept.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON } from '../constants';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { IbkrAccountSummary } from './types';

const placeIbkrOrder = vi.fn();
const gate = vi.hoisted(() => ({ reason: null as string | null }));

vi.mock('./placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: vi.fn() }));
vi.mock('./placeConfirmPrefs', () => ({ readSkipPlaceConfirm: () => true }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
  tryUnlockTicketSession: () => true,
}));
vi.mock('./marketOutsideRth', () => ({ useMarketOrdersRefused: () => gate.reason }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper', spend_status: 'paper_armed', short_enabled: true }),
}));

const SUMMARY = { connected: true, NetLiquidation: 50_000, BuyingPower: 100_000 } as IbkrAccountSummary;

describe('ManualOrderTicket market-order clock gate', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 12, mode: 'paper' });
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
    gate.reason = null;
  });

  function renderTicket() {
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="GRML"
          mode="paper"
          connected
          spendStatus="paper_armed"
          summary={SUMMARY}
          position={null}
          referencePrice={8.6}
        />,
      );
    });
  }

  const marketButton = () => mount.querySelector('[data-testid="manual-order-type-mkt"]') as HTMLButtonElement;

  async function place() {
    const form = mount.querySelector('form.manual-order-ticket') as HTMLFormElement;
    await act(async () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  }

  it('after the close: Market greys out with the reason and the Place goes out as a Limit', async () => {
    gate.reason = TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON;
    renderTicket();
    expect(marketButton().disabled).toBe(true);
    expect(marketButton().title).toBe(TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON);
    expect(marketButton().getAttribute('aria-pressed')).toBe('false');
    expect(mount.querySelector('[data-testid="market-outside-rth-note"]')?.textContent)
      .toBe(TICKER_TRADE_MARKET_OUTSIDE_RTH_REASON);
    await place();
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({ symbol: 'GRML', order_type: 'LMT' });
  });

  it('in regular hours: the Market default stands', async () => {
    renderTicket();
    expect(marketButton().disabled).toBe(false);
    expect(marketButton().getAttribute('aria-pressed')).toBe('true');
    await place();
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({ symbol: 'GRML', order_type: 'MKT' });
  });
});
