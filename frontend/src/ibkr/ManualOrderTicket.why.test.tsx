/**
 * Every locked ticket control says why (operator report 2026-09-23: "these
 * are always unclickable, at least it should explain why"). The reason rides
 * on `data-why` (ux/whyTip.ts shows it on hover and on a refused press), and
 * no native title is left to stack on it.
 *
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { TICKET_WHY_SENDING, WHY_GATEWAY_NOT_CONNECTED } from '../constantGroups/trader_chrome';
import { TopOfBookProvider, useTopOfBook, type TopOfBook } from '../hotkeys/TopOfBookContext';
import { ManualOrderFields } from './ManualOrderFields';
import { ManualOrderTicket } from './ManualOrderTicket';
import type { IbkrAccountSummary } from './types';

const placeIbkrOrder = vi.fn();

vi.mock('./placeOrder', () => ({
  placeIbkrOrder: (...args: unknown[]) => placeIbkrOrder(...args),
}));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: vi.fn() }));
vi.mock('./placeConfirmPrefs', () => ({ readSkipPlaceConfirm: () => true }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./marketOutsideRth', () => ({ useMarketOrdersRefused: () => null }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: true, mode: 'paper', spend_status: 'paper_armed', short_enabled: true }),
}));

const SUMMARY = { connected: true, NetLiquidation: 50_000, BuyingPower: 100_000 } as IbkrAccountSummary;
const BOOK: TopOfBook = { symbol: 'GRML', bid: 8.89, ask: 8.91, depthSubscribed: true };

/** Every field control the ticket locks with its own `disabled`. */
const FIELD_SELECTORS = [
  '[data-testid="manual-order-side-buy"]',
  '[data-testid="manual-order-side-sell"]',
  '[data-testid="manual-order-type-lmt"]',
  '[data-testid="manual-order-type-mkt"]',
  '[data-testid="manual-order-type-stop"]',
  '[data-testid="manual-order-stop-caret"]',
  '#manual-order-limit',
  '[data-testid="manual-order-price-bid"]',
  '[data-testid="manual-order-price-ask"]',
  '#manual-order-quantity',
  '[data-testid="manual-order-qty-mode-shares"]',
  '[data-testid="manual-order-qty-nudge-plus"]',
  '[data-testid="manual-order-extended"]',
];

function BookSetter({ book }: { book: TopOfBook | null }) {
  const { setTopOfBook } = useTopOfBook();
  useEffect(() => {
    setTopOfBook(book);
  }, [book, setTopOfBook]);
  return null;
}

describe('ManualOrderTicket says why a control is locked', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    placeIbkrOrder.mockReset();
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  function renderTicket(connected: boolean) {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <BookSetter book={BOOK} />
          <ManualOrderTicket
            symbol="GRML"
            mode="paper"
            connected={connected}
            spendStatus="paper_armed"
            summary={SUMMARY}
            position={null}
            referencePrice={8.6}
          />
        </TopOfBookProvider>,
      );
    });
  }

  const q = <T extends HTMLElement>(sel: string) => mount.querySelector(sel) as T;

  function selectLimit() {
    act(() => q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').click());
  }

  it('with no Gateway, every field and Place name the Gateway -- and no title stacks on it', () => {
    renderTicket(true);
    selectLimit();
    renderTicket(false);
    for (const sel of FIELD_SELECTORS) {
      const el = q<HTMLButtonElement>(sel);
      expect(el, sel).toBeTruthy();
      expect(el.disabled, sel).toBe(true);
      expect(el.dataset.why, sel).toBe(WHY_GATEWAY_NOT_CONNECTED);
      expect(el.hasAttribute('title'), sel).toBe(false);
    }
    const place = q<HTMLButtonElement>('[data-testid="manual-order-submit"]');
    expect(place.disabled).toBe(true);
    expect(place.dataset.why).toBe(WHY_GATEWAY_NOT_CONNECTED);
    // TIF only locks while an order is in flight.
    expect(q<HTMLButtonElement>('[data-testid="manual-order-tif-day"]').dataset.why).toBeUndefined();
  });

  it('while an order is in flight, the ticket and TIF say so, then unlock without a reason', async () => {
    let answer!: (value: unknown) => void;
    placeIbkrOrder.mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
    renderTicket(true);
    selectLimit();
    await act(async () => {
      q<HTMLFormElement>('form.manual-order-ticket')
        .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(placeIbkrOrder).toHaveBeenCalledTimes(1);
    for (const sel of [...FIELD_SELECTORS, '[data-testid="manual-order-tif-gtc"]', '[data-testid="manual-order-submit"]']) {
      expect(q<HTMLElement>(sel).dataset.why, sel).toBe(TICKET_WHY_SENDING);
    }
    expect(q<HTMLElement>('[data-testid="manual-order-tif"]').hasAttribute('title')).toBe(false);

    await act(async () => {
      answer({ ok: true, order_id: 7, mode: 'paper' });
    });
    for (const sel of FIELD_SELECTORS) {
      const el = q<HTMLButtonElement>(sel);
      expect(el.disabled, sel).toBe(false);
      expect(el.dataset.why, sel).toBeUndefined();
    }
    // No native tooltip returns either: the hover card explains the type.
    expect(q<HTMLButtonElement>('[data-testid="manual-order-type-lmt"]').hasAttribute('title')).toBe(false);
  });
});

describe('ManualOrderFields: a control\'s own block answers before the ticket lock', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('Short and Market keep their own reason; the rest carry the ticket\'s', () => {
    act(() => {
      root.render(
        <ManualOrderFields
          ticketSide="buy"
          allowShort
          orderType="LMT"
          quantityMode="shares"
          quantityValue="1"
          limitPrice="8.86"
          stopPrice=""
          outsideRth={false}
          disabled
          why={WHY_GATEWAY_NOT_CONNECTED}
          shortDisabledReason="Nova does not support short entries yet"
          marketDisabledReason="Market orders need regular hours"
          onTicketSideChange={() => undefined}
          onOrderTypeChange={() => undefined}
          onQuantityModeChange={() => undefined}
          onQuantityValueChange={() => undefined}
          onLimitPriceChange={() => undefined}
          onStopPriceChange={() => undefined}
          onOutsideRthChange={() => undefined}
        />,
      );
    });
    const why = (testId: string) =>
      (container.querySelector(`[data-testid="${testId}"]`) as HTMLElement).dataset.why;
    expect(why('manual-order-side-short')).toBe('Nova does not support short entries yet');
    expect(why('manual-order-type-mkt')).toBe('Market orders need regular hours');
    expect(why('manual-order-side-buy')).toBe(WHY_GATEWAY_NOT_CONNECTED);
    expect(why('manual-order-type-lmt')).toBe(WHY_GATEWAY_NOT_CONNECTED);
    // No book for the symbol outlives the ticket lock too.
    expect(why('manual-order-price-bid')).toBe('No live bid / ask for this symbol');
  });
});
