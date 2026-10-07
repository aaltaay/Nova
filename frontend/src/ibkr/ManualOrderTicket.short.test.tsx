/**
 * The ticket's short side (ADR 048, #778 step 3): the sides follow the position, a short is a Limit with its
 * required Buy stop, SSR prices it at the ask, the SHORT CHECK box shows the door's rules, and the order goes
 * out as a short entry carrying its stop.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { SHORT_WHY_TYPE } from '../constantGroups/short_ticket';
import { TopOfBookProvider, useTopOfBook, type TopOfBook } from '../hotkeys/TopOfBookContext';
import { requestOrderTicketPrefill } from './orderTicketPrefill';
import { ManualOrderTicket } from './ManualOrderTicket';
import { resetShortFactsForTests } from './shortFacts';
import type { IbkrAccountSummary, IbkrPosition } from './types';

const placeIbkrOrder = vi.fn();
const confirmed = vi.hoisted(() => ({ venue: 'paper' as const, generation: 'paper-test' }));
vi.mock('./confirmedDeskVenue', () => ({
  getConfirmedDeskVenueSnapshot: () => confirmed,
  subscribeConfirmedDeskVenue: () => () => {},
}));
vi.mock('./placeOrder', () => ({ placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args) }));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: vi.fn() }));
vi.mock('./placeConfirmPrefs', () => ({ readSkipPlaceConfirm: () => true }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./marketOutsideRth', () => ({ useMarketOrdersRefused: () => null }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper', spend_status: 'paper_armed', short_enabled: false }),
}));

const SUMMARY = {
  connected: true, account_class: 'margin', NetLiquidation: 5_446, BuyingPower: 20_000,
} as IbkrAccountSummary;
const BOOK: TopOfBook = { symbol: 'RDYN', bid: 5.79, ask: 5.8, depthSubscribed: true };

function checkBody(ssr: { state: string; effective_on: boolean | null }) {
  return {
    schema_version: 1, symbol: 'RDYN', venue: 'paper', ok: true, first: null,
    rules: [
      { id: 'borrow', label: 'Borrow', ok: true, state: 'ok', text: 'IBKR shows ~30,000 to borrow.', code: null,
        value: 'shortable ~30,000', numbers: {} },
      { id: 'margin', label: 'Margin', ok: true, state: 'ok', text: 'Margin: $2,080 of $5,446.', code: null,
        value: '$2,080', numbers: { requirement: 2080, liquidation_price: 13.08 } },
    ],
    facts: { bid: 5.79, ask: 5.8, ssr: { ...ssr, text: 'SSR', trigger: 4.5, prior_close: 5.0 }, halt: { state: 'none' } },
  };
}

let ssr: { state: string; effective_on: boolean | null } = { state: 'unknown', effective_on: null };
const fetchMock = vi.fn(async () => new Response(JSON.stringify(checkBody(ssr)), { status: 200 }));

function BookSetter({ book }: { book: TopOfBook | null }) {
  const { setTopOfBook } = useTopOfBook();
  useEffect(() => {
    setTopOfBook(book);
  }, [book, setTopOfBook]);
  return null;
}

describe('ManualOrderTicket: the short side (ADR 048)', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    placeIbkrOrder.mockReset();
    placeIbkrOrder.mockResolvedValue({ ok: true, order_id: 61, mode: 'paper' });
    fetchMock.mockClear();
    ssr = { state: 'unknown', effective_on: null };
    vi.stubGlobal('fetch', fetchMock);
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
    resetShortFactsForTests();
    vi.unstubAllGlobals();
  });

  function render(position: IbkrPosition | null) {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <BookSetter book={BOOK} />
          <ManualOrderTicket
            symbol="RDYN"
            mode="paper"
            connected
            spendStatus="paper_armed"
            summary={SUMMARY}
            position={position}
            referencePrice={5.79}
          />
        </TopOfBookProvider>,
      );
    });
  }

  const q = <T extends HTMLElement>(sel: string) => mount.querySelector(sel) as T;
  const side = (s: string) => q<HTMLButtonElement>(`[data-testid="manual-order-side-${s}"]`);

  async function flush() {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  function setQty(value: string) {
    const input = q<HTMLInputElement>('#manual-order-quantity');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  function typeStop(value: string) {
    const input = q<HTMLInputElement>('[data-testid="manual-order-buy-stop"]');
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  }

  async function place() {
    await act(async () => {
      q<HTMLFormElement>('form.manual-order-ticket').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  }

  it('flat: Buy / Short, with Sell saying a sale of shares you do not own is a short', () => {
    render(null);
    expect(side('buy').textContent).toBe('Buy');
    expect(side('sell').disabled).toBe(true);
    expect(side('sell').dataset.why).toMatch(/You hold no RDYN to sell/);
    expect(side('short').disabled).toBe(false);
  });

  it('long: Short is off -- Nova never flips', () => {
    render({ symbol: 'RDYN', qty: 300, avg_cost: 5.5 } as IbkrPosition);
    expect(side('short').disabled).toBe(true);
    expect(side('short').dataset.why).toMatch(/You're long RDYN: Nova never flips/);
    expect(side('sell').disabled).toBe(false);
  });

  it('Short is a Limit at the ask while SSR is not known, with its buy stop the venue offset over it', async () => {
    render(null);
    await flush();
    act(() => side('short').click());
    expect(q<HTMLButtonElement>('[data-testid="manual-order-type-mkt"]').dataset.why).toBe(SHORT_WHY_TYPE);
    expect(q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').getAttribute('aria-pressed')).toBe('true');
    expect(q<HTMLInputElement>('#manual-order-limit').value).toBe('5.80');
    expect(q<HTMLInputElement>('[data-testid="manual-order-buy-stop"]').value).toBe('5.90');
    expect(q('[data-testid="manual-order-limit-note"]').textContent).toMatch(/SSR not known yet/);
    expect(q('[data-testid="short-check"]')).toBeTruthy();
    expect(q('[data-testid="manual-order-submit"]').classList.contains('manual-order-submit--short')).toBe(true);
  });

  it('SSR known off: the short starts at the bid', async () => {
    ssr = { state: 'off', effective_on: false };
    render(null);
    await flush();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await flush();
    act(() => side('short').click());
    expect(q<HTMLInputElement>('#manual-order-limit').value).toBe('5.79');
    expect(q<HTMLInputElement>('[data-testid="manual-order-buy-stop"]').value).toBe('5.89');
    expect(mount.querySelector('[data-testid="manual-order-limit-note"]')).toBeNull();
  });

  it('places a short entry with its buy stop, and says it on the button', async () => {
    render(null);
    act(() => side('short').click());
    setQty('416');
    typeStop('5.89');
    expect(q('[data-testid="manual-order-submit"]').textContent).toBe('Short RDYN · 416 @ 5.80 · stop 5.89');
    await vi.waitFor(() => expect(q('[data-testid="short-check-rule-margin"]')).toBeTruthy());
    expect(q('[data-testid="manual-order-cost"]').textContent).toMatch(/Short\s*\$2,412\.80.*Margin\s*\$2,080/);
    await place();
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    expect(placeIbkrOrder.mock.calls[0][0]).toMatchObject({
      symbol: 'RDYN', side: 'SELL', order_type: 'LMT', qty: 416, limit_price: 5.8, short_entry: true, stop_loss_price: 5.89,
    });
    expect(placeIbkrOrder.mock.calls[0][0].take_profit_price).toBeUndefined();
  });

  it('a buy stop under the limit never leaves the ticket', async () => {
    render(null);
    act(() => side('short').click());
    typeStop('5.70');
    expect(q('[data-testid="manual-order-buy-stop-note"]').textContent).toMatch(/set it over the 5.80 limit/);
    await place();
    expect(placeIbkrOrder).not.toHaveBeenCalled();
    expect(q('[data-testid="manual-order-result"]').textContent).toMatch(/A buy stop protects a short from above/);
  });

  it('short: Cover (green) / Short more, with Sell off', () => {
    render({ symbol: 'RDYN', qty: -416, avg_cost: 5.77 } as IbkrPosition);
    expect(side('buy').textContent).toBe('Cover');
    expect(side('short').textContent).toBe('Short more');
    expect(side('sell').disabled).toBe(true);
    expect(side('sell').dataset.why).toMatch(/You're short RDYN/);
    act(() => side('buy').click());
    act(() => q<HTMLButtonElement>('[data-testid="manual-order-type-mkt"]').click());
    setQty('416');
    expect(q('[data-testid="manual-order-submit"]').textContent).toBe('Cover RDYN · 416');
    act(() => q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click());
    const submit = q('[data-testid="manual-order-submit"]');
    expect(submit.textContent).toBe('Cover RDYN · 416 @ 5.80');
    expect(submit.classList.contains('manual-order-submit--cover')).toBe(true);
    expect(q('[data-testid="manual-order-side-note"]').textContent).toMatch(/never past flat/);
  });

  it('a staged short (the plan) lands on Short with its own buy stop', () => {
    render(null);
    act(() => {
      requestOrderTicketPrefill({
        symbol: 'RDYN', side: 'SELL', orderType: 'LMT', quantityValue: '200', limitPrice: '5.77', shortEntry: true, buyStop: '5.89',
      });
    });
    expect(side('short').getAttribute('aria-pressed')).toBe('true');
    expect(q<HTMLInputElement>('#manual-order-limit').value).toBe('5.77');
    expect(q<HTMLInputElement>('[data-testid="manual-order-buy-stop"]').value).toBe('5.89');
  });

  it('a staged short while long is refused with the side\'s words, never sent as a sale', () => {
    render({ symbol: 'RDYN', qty: 100, avg_cost: 5.5 } as IbkrPosition);
    act(() => {
      requestOrderTicketPrefill({
        symbol: 'RDYN', side: 'SELL', orderType: 'LMT', quantityValue: '200', limitPrice: '5.77', shortEntry: true,
      });
    });
    expect(side('short').getAttribute('aria-pressed')).toBe('false');
    expect(q('[data-testid="manual-order-result"]').textContent).toMatch(/Nova never flips/);
  });
});
