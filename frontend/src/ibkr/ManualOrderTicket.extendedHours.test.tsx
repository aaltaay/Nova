/**
 * #169 -- ticket Place path: Extended Hours checkbox default on,
 * uncheck clears outside_rth. No Trading Hours dropdown.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { TICKER_TRADE_LABEL_TRADING_HOURS } from '../constants';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { IbkrAccountSummary } from './types';

const placeIbkrOrder = vi.fn();

vi.mock('./placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));

vi.mock('./notifyOrderRejected', () => ({
  notifyOrderRejected: vi.fn(),
}));

vi.mock('./placeConfirmPrefs', () => ({
  readSkipPlaceConfirm: () => true,
}));

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
  tryUnlockTicketSession: () => true,
}));

// This file tests the Extended Hours flag on a Market default; the market-order
// clock gate has its own test (ManualOrderTicket.marketGate.test.tsx).
vi.mock('./marketOutsideRth', () => ({
  useMarketOrdersRefused: () => null,
}));

vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
    short_enabled: true,
  }),
}));

const SUMMARY: IbkrAccountSummary = {
  connected: true,
  NetLiquidation: 50_000,
  BuyingPower: 100_000,
} as IbkrAccountSummary;

describe('ManualOrderTicket Extended Hours Place path', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 11, mode: 'paper' });
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
    vi.restoreAllMocks();
  });

  function renderTicket() {
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="SMPL"
          mode="paper"
          connected
          spendStatus="paper_armed"
          summary={SUMMARY}
          position={null}
          referencePrice={4.1}
        />,
      );
    });
  }

  function checkbox(): HTMLInputElement {
    return mount.querySelector(
      '[data-testid="manual-order-extended"]',
    ) as HTMLInputElement;
  }

  async function place() {
    const form = mount.querySelector('form.manual-order-ticket') as HTMLFormElement;
    await act(async () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  }

  it('shows an enabled Extended Hours checkbox and no hours dropdown', () => {
    renderTicket();
    const box = checkbox();
    expect(box).toBeTruthy();
    expect(box.type).toBe('checkbox');
    expect(box.checked).toBe(true);
    expect(box.disabled).toBe(false);
    expect(mount.querySelector('#manual-order-hours')).toBeNull();
    expect(mount.querySelector('select#manual-order-hours')).toBeNull();
    expect(mount.textContent).toContain(TICKER_TRADE_LABEL_TRADING_HOURS);
    expect(mount.textContent).not.toContain('Regular Hours');
  });

  it('Places Market with outside_rth true by default', async () => {
    renderTicket();
    await place();
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      symbol: 'SMPL',
      side: 'BUY',
      order_type: 'MKT',
      outside_rth: true,
    });
  });

  it('unchecking Extended Hours clears outside_rth on Place', async () => {
    renderTicket();
    act(() => {
      checkbox().click();
    });
    expect(checkbox().checked).toBe(false);
    await place();
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0].outside_rth).toBe(false);
  });

  it('keeps the checkbox enabled after Stop Limit / Trailing Stop flyout picks', () => {
    renderTicket();
    act(() => {
      const caret = mount.querySelector(
        '[data-testid="manual-order-stop-caret"]',
      ) as HTMLButtonElement;
      caret.click();
    });
    act(() => {
      const stopLimit = mount.querySelector(
        '[data-testid="manual-order-type-stop-limit"]',
      ) as HTMLButtonElement;
      stopLimit.click();
    });
    expect(checkbox().checked).toBe(true);
    expect(checkbox().disabled).toBe(false);

    act(() => {
      const caret = mount.querySelector(
        '[data-testid="manual-order-stop-caret"]',
      ) as HTMLButtonElement;
      caret.click();
    });
    act(() => {
      const trail = mount.querySelector(
        '[data-testid="manual-order-type-trail"]',
      ) as HTMLButtonElement;
      trail.click();
    });
    expect(checkbox().checked).toBe(true);
    expect(checkbox().disabled).toBe(false);
  });
});
