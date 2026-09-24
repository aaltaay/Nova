/**
 * QA D10 on the ticket (#459): `connected` is false before the first status
 * answer and after a failed poll too, and the ticket read both as "Connect IB
 * Gateway" -- blaming a Gateway nobody had heard from. Unknown stays unknown:
 * the ticket says the status is pending or failing, in the depth card's words,
 * and names the Gateway only once the status said it is down.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  TICKET_CONNECT_GATEWAY_LABEL,
  TICKET_GATEWAY_CHECKING_LABEL,
  TICKET_GATEWAY_UNKNOWN_LABEL,
  WHY_GATEWAY_NOT_CONNECTED,
  WHY_GATEWAY_STATUS_FAILED,
  WHY_GATEWAY_STATUS_PENDING,
} from '../constantGroups/trader_chrome';
import { TRADER_DEPTH_STATUS_PENDING } from '../constantGroups/trader_view';
import { TopOfBookProvider } from '../hotkeys/TopOfBookContext';
import { gatewayLockWhy, gatewayPlaceLabel, type GatewayStatusFact } from './gatewayStatusWording';
import { ManualOrderFooter } from './ManualOrderFooter';
import { ManualOrderTicket } from './ManualOrderTicket';
import { TickerTradeActionBar } from './TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrPosition } from './types';

vi.mock('./placeOrder', () => ({ placeIbkrOrder: vi.fn() }));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: vi.fn() }));
vi.mock('./placeConfirmPrefs', () => ({ readSkipPlaceConfirm: () => true }));
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => true,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./marketOutsideRth', () => ({ useMarketOrdersRefused: () => null }));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({ connected: false, mode: 'paper', spend_status: 'paper_armed', short_enabled: false }),
}));
vi.mock('../hotkeys/NovaActionRuntimeSync', () => ({ NovaActionRuntimeSync: () => null }));
vi.mock('../hotkeys/TradingQuickBar', () => ({ TradingQuickBar: () => null }));

const PENDING: GatewayStatusFact = { known: false, error: null };
const FAILING: GatewayStatusFact = { known: false, error: 'HTTP 500' };
const KNOWN: GatewayStatusFact = { known: true, error: null };

const SUMMARY = { connected: true, NetLiquidation: 50_000, BuyingPower: 100_000 } as IbkrAccountSummary;
const POSITION: IbkrPosition = {
  symbol: 'GRML', qty: 2, market_price: 9.3, market_value: 18.6, avg_cost: 9.2, unrealized_pnl: 0.2, realized_pnl: 0,
};

describe('gatewayStatusWording', () => {
  it('names the Gateway only once the status said it is down', () => {
    expect(gatewayPlaceLabel(KNOWN)).toBe(TICKET_CONNECT_GATEWAY_LABEL);
    expect(gatewayLockWhy(KNOWN)).toBe(WHY_GATEWAY_NOT_CONNECTED);
  });

  it('says the status is pending, in the depth card\'s words, before any answer', () => {
    expect(gatewayPlaceLabel(PENDING)).toBe(TICKET_GATEWAY_CHECKING_LABEL);
    expect(gatewayLockWhy(PENDING)).toBe(WHY_GATEWAY_STATUS_PENDING);
    expect(WHY_GATEWAY_STATUS_PENDING.startsWith(TRADER_DEPTH_STATUS_PENDING)).toBe(true);
  });

  it('says the status request is failing, with its reason, and never blames the Gateway', () => {
    expect(gatewayPlaceLabel(FAILING)).toBe(TICKET_GATEWAY_UNKNOWN_LABEL);
    expect(gatewayLockWhy(FAILING)).toBe(`${WHY_GATEWAY_STATUS_FAILED} (HTTP 500)`);
    for (const fact of [PENDING, FAILING]) {
      expect(gatewayPlaceLabel(fact)).not.toMatch(/connect/i);
      expect(gatewayLockWhy(fact)).not.toMatch(/not connected|reconnect/i);
    }
  });
});

describe('the ticket while the Gateway status is unknown', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    localStorage.clear();
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  const q = <T extends HTMLElement>(sel: string) => mount.querySelector(sel) as T;

  function renderFooter(gatewayStatus?: GatewayStatusFact) {
    act(() => {
      root.render(
        <ManualOrderFooter
          isPaper
          needsPinUnlock={false}
          connected={false}
          gatewayStatus={gatewayStatus}
          submitting={false}
          spendLocked={false}
          quantityLocked={false}
          forcedQty={null}
          sessionUnlocked
          result={null}
          confirmSummary={null}
          onConfirmClose={() => {}}
          onConfirmPlace={() => {}}
        />,
      );
    });
    return q<HTMLButtonElement>('[data-testid="manual-order-submit"]');
  }

  it.each([
    ['pending', PENDING, TICKET_GATEWAY_CHECKING_LABEL, WHY_GATEWAY_STATUS_PENDING],
    ['failing', FAILING, TICKET_GATEWAY_UNKNOWN_LABEL, `${WHY_GATEWAY_STATUS_FAILED} (HTTP 500)`],
    ['known down', KNOWN, TICKET_CONNECT_GATEWAY_LABEL, WHY_GATEWAY_NOT_CONNECTED],
  ])('Place while the status is %s', (_label, fact, text, why) => {
    const place = renderFooter(fact);
    expect(place.disabled).toBe(true);
    expect(place.textContent).toBe(text);
    expect(place.dataset.why).toBe(why);
  });

  it('a caller with no status of its own keeps the Gateway wording', () => {
    const place = renderFooter();
    expect(place.textContent).toBe(TICKET_CONNECT_GATEWAY_LABEL);
    expect(place.dataset.why).toBe(WHY_GATEWAY_NOT_CONNECTED);
  });

  it('every locked field of the ticket carries the unknown, not the Gateway', () => {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <ManualOrderTicket
            symbol="GRML"
            mode="paper"
            connected={false}
            gatewayStatus={PENDING}
            spendStatus="paper_armed"
            summary={SUMMARY}
            position={null}
            referencePrice={8.6}
          />
        </TopOfBookProvider>,
      );
    });
    for (const sel of ['[data-testid="manual-order-side-buy"]', '#manual-order-quantity', '[data-testid="manual-order-submit"]']) {
      const el = q<HTMLButtonElement>(sel);
      expect(el.disabled, sel).toBe(true);
      expect(el.dataset.why, sel).toBe(WHY_GATEWAY_STATUS_PENDING);
    }
    expect(q('[data-testid="manual-order-submit"]').textContent).toBe(TICKET_GATEWAY_CHECKING_LABEL);
  });

  it('the trade bar\'s own reason and a held position\'s Flatten say the status is unknown', () => {
    act(() => {
      root.render(
        <TopOfBookProvider>
          <TickerTradeActionBar
            symbol="GRML" mode="paper" connected={false} gatewayStatus={FAILING} spendStatus="paper_armed"
            position={POSITION} summary={SUMMARY} referencePrice={9.3}
          />
        </TopOfBookProvider>,
      );
    });
    const why = `${WHY_GATEWAY_STATUS_FAILED} (HTTP 500)`;
    expect(q('.ticker-trade-bar-disabled-why').textContent).toBe(why);
    const flatten = q<HTMLButtonElement>('.ticker-trade-close-btn');
    expect(flatten.disabled).toBe(true);
    expect(flatten.dataset.why).toBe(why);
    expect(mount.textContent).not.toMatch(/connect Gateway|Connect IB Gateway/);
  });
});
