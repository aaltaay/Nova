/**
 * Chart menu -> trade ticket -> `placeIbkrOrder` (#116 acceptance 4 + 6).
 *
 * The chart never places. It stages the ticket, and the ticket's existing
 * gate chain (PIN unlock, spend lock, confirm) is what finally calls the one
 * shared order helper. This test drives the real path with a mocked broker.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { stageChartOrder } from '../chart/chartOrderActions';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { IbkrAccountSummary } from './types';

const placeIbkrOrder = vi.fn();

vi.mock('./placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));

vi.mock('./notifyOrderRejected', () => ({
  notifyOrderRejected: vi.fn(),
}));

// Skip the confirm dialog: it is covered by useManualOrderSubmission tests and
// is not what this test is proving.
vi.mock('./placeConfirmPrefs', () => ({
  readSkipPlaceConfirm: () => true,
}));

vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
  tryUnlockTicketSession: () => true,
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

describe('chart menu order -> ManualOrderTicket -> placeIbkrOrder', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 42, mode: 'paper' });
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

  function limitInput(): HTMLInputElement {
    return mount.querySelector('#manual-order-limit') as HTMLInputElement;
  }

  function sidePressed(label: string): boolean {
    const group = mount.querySelector('.manual-order-side') as HTMLElement;
    const btn = Array.from(group.querySelectorAll('button')).find(
      (b) => b.textContent === label,
    );
    return btn?.getAttribute('aria-pressed') === 'true';
  }

  async function place() {
    const form = mount.querySelector('form.manual-order-ticket') as HTMLFormElement;
    await act(async () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  }

  it('Buy @ price stages a limit BUY and places it through the shared helper', async () => {
    renderTicket();
    act(() => {
      stageChartOrder({ symbol: 'SMPL', intent: 'buy', price: 4.253 });
    });

    expect(sidePressed('Buy')).toBe(true);
    expect(limitInput().value).toBe('4.25');

    await place();

    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      symbol: 'SMPL',
      side: 'BUY',
      order_type: 'LMT',
      limit_price: 4.25,
    });
    expect(placeIbkrOrder.mock.calls[0][0].qty).toBeGreaterThan(0);
  });

  it('Sell @ price stages a limit SELL without inferring a short entry', async () => {
    renderTicket();
    act(() => {
      stageChartOrder({ symbol: 'SMPL', intent: 'sell', price: 4.1 });
    });

    expect(sidePressed('Sell')).toBe(true);
    await place();

    const payload = placeIbkrOrder.mock.calls[0][0];
    expect(payload).toMatchObject({ side: 'SELL', order_type: 'LMT', limit_price: 4.1 });
    // ADR 009: opening a short needs the explicit ticket opt-in, never a
    // side+flat inference from a chart click.
    expect(payload.short_entry).toBeUndefined();
  });

  it('ignores a request staged for a different symbol', () => {
    renderTicket();
    act(() => {
      stageChartOrder({ symbol: 'SMPL', intent: 'buy', price: 4.25 });
    });
    act(() => {
      stageChartOrder({ symbol: 'AAPL', intent: 'sell', price: 250 });
    });
    expect(sidePressed('Buy')).toBe(true);
    expect(limitInput().value).toBe('4.25');
  });
});
