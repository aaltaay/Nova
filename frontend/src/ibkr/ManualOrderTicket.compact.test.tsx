/**
 * Compact ticket (approved Trader redesign, 2026-09-21): the header names the
 * venue and holds TIF, Bid / Mid / Ask set the limit from the live book, and
 * the Cost · BP after line is the same sizing the Place path runs.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { TopOfBookProvider, useTopOfBook, type TopOfBook } from '../hotkeys/TopOfBookContext';
import {
  defaultTradeDefaultsPrefs,
  readTradeDefaultsPrefs,
  writeTradeDefaultsPrefs,
} from '../settings/tradeDefaultsPrefs';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { IbkrAccountSummary, IbkrMode } from './types';

const placeIbkrOrder = vi.fn();

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
vi.mock('./marketOutsideRth', () => ({ useMarketOrdersRefused: () => null }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'paper_armed',
    short_enabled: true,
  }),
}));

const SUMMARY = { connected: true, NetLiquidation: 50_000, BuyingPower: 100_000 } as IbkrAccountSummary;
const BOOK: TopOfBook = { symbol: 'GRML', bid: 8.89, ask: 8.91, depthSubscribed: true };

function BookSetter({ book }: { book: TopOfBook | null }) {
  const { setTopOfBook } = useTopOfBook();
  useEffect(() => {
    setTopOfBook(book);
  }, [book, setTopOfBook]);
  return null;
}

describe('ManualOrderTicket compact layout', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 7, mode: 'paper' });
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  function renderTicket(opts: { book?: TopOfBook | null; mode?: IbkrMode } = {}) {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <BookSetter book={opts.book ?? null} />
          <ManualOrderTicket
            symbol="GRML"
            mode={opts.mode ?? 'paper'}
            connected
            spendStatus="paper_armed"
            summary={SUMMARY}
            position={null}
            referencePrice={8.6}
          />
        </TopOfBookProvider>,
      );
    });
  }

  const q = <T extends Element>(sel: string) => mount.querySelector(sel) as T;

  async function place() {
    const form = q<HTMLFormElement>('form.manual-order-ticket');
    await act(async () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  }

  it('heads the card with TRADE · SYM, the practice venue tag and a TIF segmented control', () => {
    renderTicket();
    const head = q<HTMLElement>('[data-testid="manual-order-header"]');
    expect(head.textContent).toContain('Trade · GRML');
    expect(head.querySelector('[data-testid="stock-view-venue-tag"]')?.textContent).toContain('PAPER');
    expect(head.textContent).toContain('fills');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-tif-day"]').getAttribute('aria-pressed')).toBe('true');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-tif-gtc"]').getAttribute('aria-pressed')).toBe('false');
    expect(mount.querySelector('.manual-order-side')?.querySelectorAll('button').length).toBe(2);
    expect(mount.querySelector('[data-testid="manual-order-type-lmt"]')).toBeTruthy();
    expect(mount.querySelector('[data-testid="manual-order-stop-caret"]')).toBeTruthy();
  });

  it('names Live plainly with no practice tag', () => {
    renderTicket({ mode: 'live' });
    const head = q<HTMLElement>('[data-testid="manual-order-header"]');
    expect(head.querySelector('[data-testid="manual-order-venue-live"]')?.textContent).toBe('LIVE');
    expect(head.querySelector('[data-testid="stock-view-venue-tag"]')).toBeNull();
  });

  it('GTC in the header writes the Trade default and rides on the next order', async () => {
    renderTicket();
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-tif-gtc"]').click();
    });
    expect(readTradeDefaultsPrefs().tif).toBe('GTC');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-tif-gtc"]').getAttribute('aria-pressed')).toBe('true');
    await place();
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({ symbol: 'GRML', tif: 'GTC' });
  });

  it('Bid / Mid / Ask set the limit from the live book and mark the one that matches', () => {
    renderTicket({ book: BOOK });
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click();
    });
    const limit = () => q<HTMLInputElement>('#manual-order-limit');
    expect(limit()).toBeTruthy();
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-mid"]').click();
    });
    expect(limit().value).toBe('8.90');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-mid"]').getAttribute('aria-pressed')).toBe('true');
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]').click();
    });
    expect(limit().value).toBe('8.89');
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]').click();
    });
    expect(limit().value).toBe('8.91');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-mid"]').getAttribute('aria-pressed')).toBe('false');
  });

  it('keeps the limit on the chosen side as the Level 2 book moves', () => {
    renderTicket({ book: BOOK });
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click();
    });
    const limit = () => q<HTMLInputElement>('#manual-order-limit');
    const ask = () => q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]');
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]').click();
    });
    act(() => ask().click());
    expect(limit().value).toBe('8.91');
    renderTicket({ book: { ...BOOK, bid: 8.92, ask: 8.95 } });
    expect(limit().value).toBe('8.95');
    expect(ask().getAttribute('aria-pressed')).toBe('true');
    expect(ask().title).toMatch(/^Following the live ask: 8\.95/);

    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]').click();
    });
    renderTicket({ book: { ...BOOK, bid: 8.97, ask: 8.99 } });
    expect(limit().value).toBe('8.97');

    // Clicking the lit button stops following and leaves the price.
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]').click();
    });
    renderTicket({ book: { ...BOOK, bid: 9.01, ask: 9.03 } });
    expect(limit().value).toBe('8.97');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]').getAttribute('aria-pressed')).toBe('false');
  });

  it('a typed price stops following the book', () => {
    renderTicket({ book: BOOK });
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click();
    });
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]').click();
    });
    const input = q<HTMLInputElement>('#manual-order-limit');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(input, '8.80');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    renderTicket({ book: { ...BOOK, bid: 8.92, ask: 8.95 } });
    expect(q<HTMLInputElement>('#manual-order-limit').value).toBe('8.80');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]').getAttribute('aria-pressed')).toBe('false');
  });

  it('a Limit seeded from the ask keeps following it, and holds when the book goes', () => {
    writeTradeDefaultsPrefs({ ...defaultTradeDefaultsPrefs(), orderType: 'LMT' });
    renderTicket({ book: BOOK });
    const limit = () => q<HTMLInputElement>('#manual-order-limit');
    expect(limit().value).toBe('8.91');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]').getAttribute('aria-pressed')).toBe('true');
    renderTicket({ book: { ...BOOK, bid: 8.92, ask: 8.94 } });
    expect(limit().value).toBe('8.94');
    renderTicket({ book: { ...BOOK, ask: null } });
    expect(limit().value).toBe('8.94');
    expect(q<HTMLButtonElement>('[data-testid="manual-order-price-ask"]').title).toMatch(/holds until the book returns/);
  });

  it('greys Bid / Mid / Ask with the reason when there is no live book for the symbol', () => {
    renderTicket({ book: { ...BOOK, symbol: 'QNME' } });
    act(() => {
      q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click();
    });
    const bid = q<HTMLButtonElement>('[data-testid="manual-order-price-bid"]');
    expect(bid.disabled).toBe(true);
    expect(bid.title).toBe('No live bid / ask for this symbol');
  });

  it('shows Cost · BP after from the same sizing the Place path uses', () => {
    renderTicket();
    // Market default, 100 shares at the 8.60 reference against $100,000 of buying power.
    const cost = q<HTMLElement>('[data-testid="manual-order-cost"]');
    expect(cost.textContent).toContain('$860.00');
    expect(cost.textContent).toContain('$99,140');
  });

  it('prefixes the result with Last: and the est chip on a practice venue', async () => {
    renderTicket();
    await place();
    const result = q<HTMLElement>('[data-testid="manual-order-result"]');
    expect(result.textContent).toContain('Last:');
    expect(result.textContent).toContain('Order #7 placed');
    expect(result.querySelector('[data-testid="est-chip"]')).toBeTruthy();
  });
});
