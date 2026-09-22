/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IbkrAccountSummary } from '../ibkr/types';
import type { IbkrClientStatus } from '../ibkr/useIbkrStatus';
import { PAPER_ACCOUNT as PAPER } from '../practice/practiceFixtures';
import type { PracticeAccount } from '../practice/practiceTypes';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';

const { status, practice } = vi.hoisted(() => ({
  status: { current: {} as IbkrClientStatus },
  practice: { current: { data: null as PracticeAccount | null, error: null as string | null } },
}));
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => status.current }));
vi.mock('../practice/practiceAccountResource', () => ({ usePracticeAccount: () => practice.current }));

function baseStatus(overrides: Partial<IbkrClientStatus> = {}): IbkrClientStatus {
  return {
    enabled: true,
    connected: true,
    transport_connected: true,
    session_reason: 'ok',
    mode: 'live',
    venue: 'live',
    orders_enabled: false,
    short_enabled: false,
    spend_status: 'locked',
    trading_allowed: false,
    trading_allowed_reason: null,
    market_data_type: 1,
    market_data_delayed: false,
    account_id: 'U1234567',
    account_ids: ['U1234567'],
    broker_account_kind: 'live',
    clientReady: true,
    stale: false,
    staleSince: null,
    ...overrides,
  };
}

const LIVE_SUMMARY: IbkrAccountSummary = {
  connected: true,
  mode: 'live',
  AccountType: 'INDIVIDUAL',
  account_class: 'margin',
  NetLiquidation: 3559.55,
  TotalCashValue: 3558.53,
  BuyingPower: 7117.06,
  ExcessLiquidity: 3000,
  UnrealizedPnL: -0.17,
  RealizedPnL: 12.5,
  GrossPositionValue: 1.02,
};

const SIM: PracticeAccount = {
  ...PAPER,
  venue: 'sim',
  account_id: 'NOVA-SIM',
  replay_key: 'capture:AAPL:2026-09-19',
};

function mount(overrides: Partial<Parameters<typeof GlobalBarAccountCluster>[0]> = {}) {
  render(
    <GlobalBarAccountCluster
      accountChrome="ready"
      accountError={null}
      summary={LIVE_SUMMARY}
      orders={[]}
      closedOrders={[]}
      traderActive={false}
      closeTraderView={() => {}}
      refresh={() => {}}
      venue="live"
      {...overrides}
    />,
  );
}

function click(testId: string) {
  act(() => {
    (screen.getByTestId(testId) as HTMLButtonElement).click();
  });
}

beforeEach(() => {
  status.current = baseStatus();
  practice.current = { data: null, error: null };
});

afterEach(cleanup);

describe('GlobalBarAccountCluster -- Live (the IBKR account)', () => {
  it("renders Day's | Working | TAV | pill on one row, in that order", () => {
    mount({
      orders: [{ order_id: 1, symbol: 'AAPL', side: 'BUY', qty: 1, order_type: 'MKT', status: 'Submitted' }],
    });
    const cluster = screen.getByTestId('global-bar-cluster');
    const day = screen.getByTestId('global-bar-account-trigger');
    expect(day.textContent).toContain("Day's");
    expect(day.textContent).toContain('+$12.33');
    expect(screen.getByTestId('global-bar-day-pct').textContent).toBe('+0.35%');
    expect(screen.getByTestId('global-bar-working-trigger').textContent).toContain('1');
    expect(screen.getByTestId('global-bar-tav-trigger').textContent).toContain('$3,559.55');
    const pill = screen.getByTestId('global-bar-account-pill');
    expect(pill.textContent).toContain('Individual Margin (U1234567)');
    expect(pill.dataset.kind).toBe('live');
    const order = Array.from(cluster.querySelectorAll('button')).map((b) => b.dataset.testid);
    expect(order).toEqual([
      'global-bar-account-trigger',
      'global-bar-working-trigger',
      'global-bar-tav-trigger',
      'global-bar-account-pill',
    ]);
    // Cash and BP live in the cards, not on the row.
    expect(cluster.textContent).not.toContain('$3,558.53');
    expect(cluster.textContent).not.toContain('$7,117.06');
    expect(screen.getByTestId('global-bar-account').dataset.source).toBe('ibkr');
  });

  it("Day's card: Open, Day's, Day's Realized -- no Fees row on IBKR", () => {
    mount();
    click('global-bar-account-trigger');
    const card = screen.getByTestId('global-bar-day-card');
    expect(card.textContent).toContain('Open P&L');
    expect(card.textContent).toContain('-$0.17');
    expect(card.textContent).toContain("Day's P&L");
    expect(card.textContent).toContain('+$12.33');
    expect(card.textContent).toContain("Day's Realized P&L");
    expect(card.textContent).toContain('+$12.50');
    expect(screen.queryByTestId('global-bar-card-fees')).toBeNull();
  });

  it('TAV card: TAV, Cash, Buying Power, Excess Liquidity, Gross Position Value', () => {
    mount();
    click('global-bar-tav-trigger');
    const card = screen.getByTestId('global-bar-tav-card');
    expect(card.textContent).toContain('Total Account Value');
    expect(card.textContent).toContain('$3,559.55');
    expect(card.textContent).toContain('Cash');
    expect(card.textContent).toContain('$3,558.53');
    expect(card.textContent).toContain('Buying Power');
    expect(card.textContent).toContain('$7,117.06');
    expect(screen.getByTestId('global-bar-card-excess').textContent).toContain('$3,000.00');
    expect(card.textContent).toContain('Gross Position Value');
    expect(card.textContent).toContain('$1.02');
    expect(screen.queryByTestId('global-bar-card-starting-cash')).toBeNull();
    expect(screen.queryByTestId('global-bar-card-replay')).toBeNull();
  });

  it('omits Excess Liquidity when IBKR does not report it, and the percent when the base is not > 0', () => {
    mount({ summary: { ...LIVE_SUMMARY, ExcessLiquidity: null, NetLiquidation: 12.33 } });
    expect(screen.queryByTestId('global-bar-day-pct')).toBeNull();
    click('global-bar-tav-trigger');
    expect(screen.queryByTestId('global-bar-card-excess')).toBeNull();
  });

  it('one menu at a time; Escape closes it', () => {
    mount();
    click('global-bar-account-trigger');
    expect(screen.getByTestId('global-bar-day-card')).toBeTruthy();
    click('global-bar-account-pill');
    expect(screen.queryByTestId('global-bar-day-card')).toBeNull();
    const menu = screen.getByTestId('global-bar-account-pill-menu');
    expect(menu.textContent).toContain('U1234567');
    expect(menu.textContent).toContain('active');
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    });
    expect(screen.queryByTestId('global-bar-account-pill-menu')).toBeNull();
  });

  it('keeps the pill (id only) while the account snapshot is loading, and drops it while disconnected', () => {
    mount({ accountChrome: 'loading', summary: null });
    const chip = screen.getByTestId('global-bar-offline');
    expect(chip.dataset.chrome).toBe('loading');
    expect(chip.textContent).toContain('Account…');
    expect(chip.textContent).toContain('TAV');
    expect(chip.textContent).toContain('--');
    expect(screen.getByTestId('global-bar-account-pill').textContent).toContain('U1234567');
    cleanup();
    status.current = baseStatus({ connected: false, mode: 'disconnected', account_id: null, account_ids: [] });
    mount({ accountChrome: 'offline', summary: null, venue: 'disconnected' });
    expect(screen.getByTestId('global-bar-offline').textContent).toContain('IBKR offline');
    expect(screen.queryByTestId('global-bar-cluster')).toBeNull();
    expect(screen.queryByTestId('global-bar-account-pill')).toBeNull();
  });

  it('says Account unavailable (with the reason) when Gateway is up but the poll failed', () => {
    mount({ accountChrome: 'unavailable', accountError: 'account (HTTP 503)', summary: null });
    const chip = screen.getByTestId('global-bar-offline');
    expect(chip.dataset.chrome).toBe('unavailable');
    expect(chip.textContent).toContain('Account unavailable');
    expect(chip.title).toContain('account (HTTP 503)');
  });
});

describe('GlobalBarAccountCluster -- practice venues (ADR 020)', () => {
  it('shows NOVA-PAPER figures on Paper even though the live Gateway also has an IBKR summary', () => {
    status.current = baseStatus({ mode: 'paper', venue: 'paper', account_id: 'NOVA-PAPER', account_ids: ['NOVA-PAPER'] });
    practice.current = { data: PAPER, error: null };
    mount({ venue: 'paper' });
    const cluster = screen.getByTestId('global-bar-cluster');
    expect(screen.getByTestId('global-bar-account').dataset.source).toBe('practice');
    expect(screen.getByTestId('global-bar-account-trigger').textContent).toContain('+$250.25');
    expect(screen.getByTestId('global-bar-day-pct').textContent).toBe('+0.25%');
    expect(screen.getByTestId('global-bar-tav-trigger').textContent).toContain('$101,200.25');
    expect(cluster.textContent).not.toContain('$3,559.55');
    const pill = screen.getByTestId('global-bar-account-pill');
    expect(pill.textContent).toContain('Nova Paper Margin (NOVA-PAPER)');
    expect(pill.dataset.kind).toBe('practice');
    expect(pill.title).toMatch(/fake money/i);
    expect(pill.textContent).not.toContain('Individual');
    click('global-bar-account-trigger');
    expect(screen.getByTestId('global-bar-day-card').textContent).toContain('+$350.25');
    expect(screen.getByTestId('global-bar-card-fees').textContent).toContain('$3.50');
    click('global-bar-tav-trigger');
    const tav = screen.getByTestId('global-bar-tav-card');
    expect(tav.textContent).toContain('$98,750.50');
    expect(tav.textContent).toContain('$395,002.00');
    expect(tav.textContent).toContain('$2,449.75');
    expect(screen.getByTestId('global-bar-card-starting-cash').textContent).toContain('$100,000.00');
    expect(screen.queryByTestId('global-bar-card-excess')).toBeNull();
    expect(screen.queryByTestId('global-bar-card-replay')).toBeNull();
  });

  it('Sim: NOVA-SIM pill and the replay row, stated as absent when nothing is loaded', () => {
    status.current = baseStatus({ mode: 'sim', venue: 'sim', account_id: 'NOVA-SIM', account_ids: ['NOVA-SIM'] });
    practice.current = { data: SIM, error: null };
    mount({ venue: 'sim' });
    expect(screen.getByTestId('global-bar-account-pill').textContent).toContain('Nova Sim Margin (NOVA-SIM)');
    click('global-bar-tav-trigger');
    const replay = screen.getByTestId('global-bar-card-replay');
    expect(replay.textContent).toContain('capture:AAPL:2026-09-19');
    expect(replay.classList.contains('is-empty')).toBe(false);
    cleanup();
    practice.current = { data: { ...SIM, replay_key: null }, error: null };
    mount({ venue: 'sim' });
    click('global-bar-tav-trigger');
    const empty = screen.getByTestId('global-bar-card-replay');
    expect(empty.textContent).toContain('No replay loaded');
    expect(empty.classList.contains('is-empty')).toBe(true);
  });

  it('follows the practice poll, not the IBKR summary: loading, unavailable, and a stale other-venue snapshot', () => {
    status.current = baseStatus({ mode: 'paper', venue: 'paper', account_id: 'NOVA-PAPER', account_ids: ['NOVA-PAPER'] });
    mount({ venue: 'paper' });
    let chip = screen.getByTestId('global-bar-offline');
    expect(chip.dataset.chrome).toBe('loading');
    expect(chip.textContent).toContain('Practice account loading');
    expect(chip.textContent).not.toContain('IBKR offline');
    // The venue's id is a constant, so the pill can say it before the ledger loads.
    expect(screen.getByTestId('global-bar-account-pill').textContent).toContain('Nova Paper Margin (NOVA-PAPER)');
    cleanup();
    practice.current = { data: null, error: 'practice ledger locked' };
    mount({ venue: 'paper' });
    chip = screen.getByTestId('global-bar-offline');
    expect(chip.dataset.chrome).toBe('unavailable');
    expect(chip.textContent).toMatch(/unavailable/i);
    expect(chip.title).toContain('practice ledger locked');
    expect(screen.queryByTestId('global-bar-cluster')).toBeNull();
    cleanup();
    practice.current = { data: SIM, error: null };
    mount({ venue: 'paper' });
    expect(screen.getByTestId('global-bar-offline').dataset.chrome).toBe('loading');
  });
});
