/**
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManualOrderTicket } from './ManualOrderTicket';
import { placeActionLabel } from './ticketSide';
import type { IbkrAccountSummary } from './types';
import type { IbkrListingFlags } from '../types/ticker';

// The Sim venue reads its clock; no request leaves the test.
vi.mock('../api/novaFetch', () => ({ novaFetch: vi.fn(async () => { throw new TypeError('offline'); }) }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));

// Side vs account class is an IBKR (Live) question: the practice venues never short (below).
const venue = vi.hoisted(() => ({ mode: 'live' as 'live' | 'paper' | 'sim' }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: venue.mode,
    spend_status: `${venue.mode}_armed`,
    short_enabled: true,
  }),
}));

const SHORTABLE: IbkrListingFlags = {
  source: 'ibkr',
  connected: true,
  state: 'shortable_est',
  stale: false,
  orderable: true,
};

describe('ManualOrderTicket Side vs account_class', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    venue.mode = 'live';
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

  function render(summary: IbkrAccountSummary) {
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="NVDA"
          mode={venue.mode}
          connected
          spendStatus={`${venue.mode}_armed`}
          summary={summary}
          position={null}
          referencePrice={100}
          listingIbkr={SHORTABLE}
        />,
      );
    });
  }

  it('hides Direction and Short on Cash including INDIVIDUAL', () => {
    render({
      connected: true,
      mode: 'paper',
      AccountType: 'INDIVIDUAL',
      account_class: 'cash',
      BuyingPower: 4000,
    });
    expect(container.textContent).not.toContain('Direction');
    expect(container.querySelector('[data-testid="manual-order-side-short"]')).toBeNull();
    expect(container.querySelector('[data-testid="manual-order-side-buy"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="manual-order-side-sell"]')).toBeTruthy();
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn.textContent).toBe(placeActionLabel('buy', 'NVDA'));
  });

  it('does not invent Short from BuyingPower alone', () => {
    render({
      connected: true,
      mode: 'paper',
      BuyingPower: 50_000,
    });
    expect(container.querySelector('[data-testid="manual-order-side-short"]')).toBeNull();
  });

  it('shows Short on Margin and labels Place Short SYMBOL', () => {
    render({
      connected: true,
      mode: 'paper',
      AccountType: 'INDIVIDUAL',
      account_class: 'margin',
      BuyingPower: 50_000,
    });
    const short = container.querySelector(
      '[data-testid="manual-order-side-short"]',
    ) as HTMLButtonElement;
    expect(short).toBeTruthy();
    act(() => {
      short.click();
    });
    expect(short.getAttribute('aria-pressed')).toBe('true');
    expect(
      container
        .querySelector('[data-testid="manual-order-side-sell"]')
        ?.getAttribute('aria-pressed'),
    ).toBe('false');
    const btn = container.querySelector('.manual-order-submit') as HTMLButtonElement;
    expect(btn.textContent).toBe(placeActionLabel('short', 'NVDA'));
    expect(btn.classList.contains('manual-order-submit--short')).toBe(true);
  });

  it.each(['paper', 'sim'] as const)('on %s the Short is refused with Nova\'s reason, however shortable the symbol (V13)', (mode) => {
    venue.mode = mode;
    render({
      connected: true,
      mode,
      AccountType: 'INDIVIDUAL',
      account_class: 'margin',
      BuyingPower: 50_000,
    });
    const short = container.querySelector('[data-testid="manual-order-side-short"]') as HTMLButtonElement;
    expect(short).toBeTruthy();
    expect(short.disabled).toBe(true);
    expect(short.title).toBe('Nova does not support short entries yet');
    expect(container.textContent).not.toMatch(/check TWS/);
  });
});
