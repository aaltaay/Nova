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

// Side vs account class; the practice venues short through the same Short side (below, ADR 048).
const venue = vi.hoisted(() => ({
  mode: 'live' as 'live' | 'paper' | 'sim',
  // The Live short proof (ADR 048 step 6): complete here unless a test says otherwise.
  proof: { complete: true, done: 7, total: 7 } as { complete: boolean; done: number; total: number } | null,
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: venue.mode,
    spend_status: `${venue.mode}_armed`,
    short_enabled: true,
    short_proof: venue.proof,
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
    venue.proof = { complete: true, done: 7, total: 7 };
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

  it('locks a Live short while the Live short proof is incomplete, and says so', () => {
    venue.proof = { complete: false, done: 2, total: 7 };
    render({
      connected: true,
      mode: 'live',
      AccountType: 'INDIVIDUAL',
      account_class: 'margin',
      ibkr_account_class: 'margin',
      BuyingPower: 50_000,
    });
    const short = container.querySelector('[data-testid="manual-order-side-short"]') as HTMLButtonElement;
    expect(short).toBeTruthy();
    expect(short.disabled || short.getAttribute('aria-disabled') === 'true').toBe(true);
    expect(short.getAttribute('data-why')).toContain('Live short proof is not complete (2 of 7 days and drills)');
  });

  it('gives Live no Short side when only the .env override says margin', () => {
    render({
      connected: true,
      mode: 'live',
      AccountType: 'INDIVIDUAL',
      account_class: 'margin',
      ibkr_account_class: 'cash',
      account_class_source: 'override',
      BuyingPower: 383,
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
    // ADR 048: the short's own words -- size, price and its buy stop -- in orange.
    expect(btn.textContent?.startsWith(placeActionLabel('short', 'NVDA'))).toBe(true);
    expect(btn.classList.contains('manual-order-submit--short')).toBe(true);
  });

  it.each(['paper', 'sim'] as const)('on %s the Short opens whatever the listing says: the short check decides (ADR 048)', (mode) => {
    venue.mode = mode;
    act(() => {
      root.render(
        <ManualOrderTicket
          symbol="NVDA"
          mode={mode}
          connected
          spendStatus={`${mode}_armed`}
          summary={{ connected: true, mode, AccountType: 'INDIVIDUAL', account_class: 'margin', BuyingPower: 50_000 }}
          position={null}
          referencePrice={100}
          listingIbkr={null}
        />,
      );
    });
    const short = container.querySelector('[data-testid="manual-order-side-short"]') as HTMLButtonElement;
    expect(short).toBeTruthy();
    expect(short.disabled).toBe(false);
    expect(short.dataset.why).toBeUndefined();
    expect(container.textContent).not.toMatch(/check TWS/);
  });
});
