/**
 * A disarmed desk can always get flat (ADR 018). The rail's Flatten is sent as
 * the protective `flatten` source, which the backend's arm latch never holds,
 * yet it was greyed out -- and its only way forward was to arm the desk --
 * whenever the padlock was locked. It now answers only to the locks the
 * backend holds a flatten to, and never arms; the ticket's Place still does.
 *
 * @vitest-environment jsdom
 */
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CLOSE_POSITION_ACCOUNT_ERROR_TITLE,
  CLOSE_POSITION_BUSY_WHY,
  CLOSE_POSITION_DISARMED_TITLE,
  CLOSE_POSITION_NO_POSITION_TITLE,
  TICKER_TRADE_UNLOCK_LABEL,
} from '../constants';
import { TopOfBookProvider } from '../hotkeys/TopOfBookContext';
import { spendLockReason } from './spendLock';
import { TickerTradeActionBar } from './TickerTradeActionBar';
import type { IbkrAccountSummary, IbkrMode, IbkrPosition } from './types';

const mocks = vi.hoisted(() => ({
  close: vi.fn(),
  confirm: vi.fn(),
  notify: vi.fn(),
  // The one arm flow. Flatten must never go through it, so it refuses here.
  ensureUnlocked: vi.fn(async () => false),
}));

vi.mock('../ux', () => ({
  confirmApp: (...args: unknown[]) => mocks.confirm(...args),
  alertApp: async () => undefined,
}));
vi.mock('./useTradingPinGate', () => ({
  useTradingPinGate: () => ({ ensureUnlocked: () => mocks.ensureUnlocked(), pinDialog: null }),
}));
vi.mock('./closeFullPosition', () => ({ closeFullPosition: (...args: unknown[]) => mocks.close(...args) }));
vi.mock('./notifyOrderRejected', () => ({ notifyOrderRejected: (...args: unknown[]) => mocks.notify(...args) }));
vi.mock('../hotkeys/NovaActionRuntimeSync', () => ({ NovaActionRuntimeSync: () => null }));
vi.mock('../hotkeys/TradingQuickBar', () => ({ TradingQuickBar: () => null }));
// What the backend reports while disarmed.
vi.mock('./ticketUnlock', () => ({
  readTicketSessionUnlocked: () => false,
  subscribeTicketSessionUnlock: () => () => {},
}));
vi.mock('./useIbkrStatus', () => ({
  useIbkrStatus: () => ({
    connected: true,
    mode: 'paper',
    spend_status: 'locked_disarmed',
    armed: false,
    trading_allowed: false,
    trading_allowed_reason: 'Desk is disarmed -- arm trading in this session before placing',
    short_enabled: false,
  }),
}));

const SUMMARY = { connected: true, NetLiquidation: 100_000, BuyingPower: 400_000 } as IbkrAccountSummary;
const POSITION: IbkrPosition = {
  symbol: 'GRML', qty: 2, market_price: 9.3, market_value: 18.6, avg_cost: 9.2, unrealized_pnl: 0.2, realized_pnl: 0,
};

describe('the rail Flatten on a disarmed desk (ADR 018)', () => {
  let mount: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.close.mockReset();
    mocks.notify.mockReset();
    mocks.ensureUnlocked.mockClear();
    mocks.confirm.mockReset();
    mocks.confirm.mockResolvedValue(true);
    mount = document.createElement('div');
    document.body.appendChild(mount);
    root = createRoot(mount);
  });

  afterEach(() => {
    act(() => root.unmount());
    mount.remove();
  });

  async function render(props: {
    mode?: IbkrMode;
    connected?: boolean;
    spendStatus?: string;
    accountError?: string | null;
    position?: IbkrPosition | null;
  } = {}) {
    // Async act: the ticket inside the bar settles its own effects before any assert.
    await act(async () => {
      root.render(
        <TopOfBookProvider>
          <TickerTradeActionBar
            symbol="GRML"
            mode={props.mode ?? 'paper'}
            connected={props.connected ?? true}
            spendStatus={'spendStatus' in props ? props.spendStatus : 'locked_disarmed'}
            accountError={props.accountError ?? null}
            position={props.position === undefined ? POSITION : props.position}
            summary={SUMMARY}
            referencePrice={9.3}
          />
        </TopOfBookProvider>,
      );
    });
    return mount.querySelector('.ticker-trade-close-btn') as HTMLButtonElement;
  }

  it.each<IbkrMode>(['live', 'paper', 'sim'])(
    'Flatten is unlocked on %s, while the ticket still needs the padlock to place',
    async (mode) => {
      const flatten = await render({ mode });
      expect(flatten.textContent).toBe('Flatten 2');
      expect(flatten.disabled).toBe(false);
      expect(flatten.dataset.why).toBeUndefined();
      expect(flatten.title).toBe(CLOSE_POSITION_DISARMED_TITLE);
      // Nothing that opens a position changed: Place still asks to unlock first.
      const place = mount.querySelector('[data-testid="manual-order-submit"]');
      expect(place?.textContent).toBe(TICKER_TRADE_UNLOCK_LABEL);
      expect(mount.querySelector('.ticker-trade-bar-disabled-why')?.textContent).toBe(
        spendLockReason('locked_disarmed'),
      );
    },
  );

  it('sends the flatten after the confirm and never asks to arm the desk', async () => {
    mocks.close.mockResolvedValue({
      ok: true, order_id: 9, side: 'SELL', qty: 2, mode: 'live', outside_rth: false, order_type: 'MKT',
    });
    const flatten = await render({ mode: 'live' });
    await act(async () => { flatten.click(); });
    await act(async () => { await Promise.resolve(); });
    expect(mocks.ensureUnlocked).not.toHaveBeenCalled();
    expect(mocks.confirm).toHaveBeenCalledOnce();
    expect(mocks.close).toHaveBeenCalledWith('GRML', 2, expect.objectContaining({ mode: 'live' }));
    expect(mount.querySelector('[data-testid="manual-order-result"]')?.textContent).toContain('Flatten order #9');
  });

  it('does not send when the confirm is declined', async () => {
    mocks.confirm.mockResolvedValue(false);
    const flatten = await render();
    await act(async () => { flatten.click(); });
    expect(mocks.close).not.toHaveBeenCalled();
  });

  it('stays locked, and says why, with no position, no Gateway, or a failed account read', async () => {
    const cases: [Parameters<typeof render>[0], string | RegExp][] = [
      [{ position: null }, CLOSE_POSITION_NO_POSITION_TITLE],
      [{ position: { ...POSITION, qty: 0 } }, CLOSE_POSITION_NO_POSITION_TITLE],
      [{ connected: false }, /IBKR disconnected/],
      [{ mode: 'disconnected' }, 'IBKR mode offline'],
      [{ accountError: 'positions read failed' }, CLOSE_POSITION_ACCOUNT_ERROR_TITLE],
    ];
    for (const [props, why] of cases) {
      const flatten = await render(props);
      expect(flatten.disabled).toBe(true);
      if (typeof why === 'string') expect(flatten.dataset.why).toBe(why);
      else expect(flatten.dataset.why).toMatch(why);
    }
  });

  it('stays locked while its own flatten is in flight', async () => {
    let answer!: (value: unknown) => void;
    mocks.close.mockImplementation(() => new Promise((resolve) => { answer = resolve; }));
    const flatten = await render();
    await act(async () => { flatten.click(); });
    expect(flatten.disabled).toBe(true);
    expect(flatten.dataset.why).toBe(CLOSE_POSITION_BUSY_WHY);
    await act(async () => {
      answer({ ok: true, order_id: 4, side: 'SELL', qty: 2, mode: 'paper', outside_rth: false, order_type: 'MKT' });
    });
    expect(flatten.disabled).toBe(false);
  });

  it.each(['locked', 'locked_live_unconfirmed', 'locked_account_unconfirmed', undefined])(
    'keeps the %s lock and its reason -- the backend refuses a flatten there too',
    async (spendStatus) => {
      const flatten = await render({ mode: 'live', spendStatus });
      expect(flatten.disabled).toBe(true);
      expect(flatten.dataset.why).toBe(spendLockReason(spendStatus));
    },
  );
});
