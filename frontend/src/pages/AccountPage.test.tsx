/** @vitest-environment jsdom */
import { act } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PAPER_ACCOUNT_TODAY, paperHistoryFixture } from '../account/accountFixtures';
import { resetAccountHistoryResourcesForTests } from '../account/accountHistoryResource';
import { ACCOUNT_LIVE_NO_LEDGER } from '../constantGroups/account_page';
import type { IbkrAccountSummary, IbkrOrder } from '../ibkr/types';
import { AccountPage } from './AccountPage';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  confirm: vi.fn(),
  workspace: { ibkrMode: 'paper' as string, selectedSymbol: null as string | null, setSelectedSymbol: vi.fn(), ibkrConnected: true },
  ibkr: {
    summary: null as IbkrAccountSummary | null,
    positions: [] as unknown[],
    orders: [] as IbkrOrder[],
    closedOrders: [] as IbkrOrder[],
    loading: false,
    error: null as string | null,
    stale: false,
    staleSince: null as number | null,
    refresh: vi.fn(),
  },
  bot: { session: null as unknown },
}));

vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../ux', () => ({ confirmApp: (...args: unknown[]) => mocks.confirm(...args) }));
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => mocks.workspace }));
vi.mock('../ibkr/IbkrAccountContext', () => ({
  useIbkrAccountContext: () => mocks.ibkr,
  useOptionalIbkrAccountContext: () => mocks.ibkr,
}));
vi.mock('../bot/useBotSession', () => ({ useBotSession: () => mocks.bot }));
// The page follows the status's own venue (C26); here it states none, so the workspace mode decides.
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ({ mode: mocks.workspace.ibkrMode }) }));
vi.mock('../ibkr/TradingTab', () => ({
  TradingTab: ({ initialSection, sections, showTicket }: { initialSection?: string; sections?: string[]; showTicket?: boolean }) => (
    <div
      data-testid="legacy-trading-tab"
      data-section={initialSection}
      data-sections={(sections ?? []).join(',')}
      data-ticket={showTicket === false ? 'off' : 'on'}
    />
  ),
}));

const ORDER: IbkrOrder = {
  order_id: 6, symbol: 'GRML', side: 'BUY', qty: 100, order_type: 'MKT', limit_price: null,
  avg_fill_price: 8.8, fill_estimated: true, status: 'Filled', filled_qty: 100, filled_at: '2026-09-21T19:47:18Z',
};
const EXPIRED: IbkrOrder = {
  order_id: 7, symbol: 'GRML', side: 'SELL', qty: 100, order_type: 'LMT', limit_price: 9.5, status: 'Expired', submitted_at: '2026-09-21T19:50:00Z',
};

beforeEach(() => {
  resetAccountHistoryResourcesForTests();
  mocks.fetch.mockReset();
  mocks.confirm.mockReset();
  mocks.confirm.mockResolvedValue(true);
  mocks.workspace.ibkrMode = 'paper';
  mocks.ibkr.summary = null;
  mocks.ibkr.orders = [];
  mocks.ibkr.closedOrders = [];
  mocks.bot.session = null;
  mocks.fetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const u = String(url);
    if (u.includes('/api/practice/history')) return { ok: true, status: 200, json: async () => paperHistoryFixture() };
    if (u.includes('/api/practice/reset')) {
      expect(init?.method).toBe('POST');
      return { ok: true, status: 200, json: async () => ({ ...PAPER_ACCOUNT_TODAY, cash: 100000, net_liquidation: 100000, positions: [] }) };
    }
    if (u.includes('/api/practice/account')) return { ok: true, status: 200, json: async () => PAPER_ACCOUNT_TODAY };
    return { ok: false, status: 404, json: async () => ({}) };
  });
});

afterEach(cleanup);

describe('AccountPage', () => {
  it('on Paper reads the ledger and its history: TAV, rows that add up, ledger rows, calendar and components', async () => {
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-tav').textContent).toBe('$100,142.10'));
    await waitFor(() => expect(screen.getByTestId('account-rows-reconcile').getAttribute('data-reconcile')).toBe('ok'));
    expect(screen.getByTestId('account-page').getAttribute('data-venue')).toBe('paper');
    expect(screen.getByTestId('account-page-venue').textContent).toContain('NOVA-PAPER');
    // Realized today is net of commissions and fees, as the ledger books it (QA V1).
    expect(screen.getByTestId('account-rows').textContent).toContain('+$87.10');
    expect(screen.getByTestId('account-rows').textContent).toContain('-$10.00');
    expect(screen.getByTestId('account-rows').textContent).toContain('-$0.40');
    expect(screen.getByTestId('account-equity-curve')).toBeTruthy();
    expect(screen.getAllByTestId('account-ledger-row-fill')).toHaveLength(6);
    expect(screen.getByTestId('account-ledger-row-start')).toBeTruthy();
    expect(screen.getByTestId('account-ledger-row-reset').textContent).toContain('practice-paper-2026-09-18T1612.json');
    expect(screen.getByTestId('account-ledger-foot').textContent).toContain('practice-paper.json');
    expect(screen.getByTestId('account-comp-ring-realized').getAttribute('data-share')).toBe((97.5 / 162.9).toFixed(3));
    expect(screen.getByTestId('account-calendar-grid')).toBeTruthy();
    expect(screen.getByTestId('account-breakers').textContent).toMatch(/not exposed/);
    expect(screen.queryByTestId('account-page-tab-broker')).toBeNull();
    expect(screen.getByTestId('account-reset-button')).toBeTruthy();
    // No history request goes out for Live and none is fabricated here: every call names a practice venue.
    for (const call of mocks.fetch.mock.calls) expect(String(call[0])).toMatch(/venue=paper/);
  });

  it('Performance switches tabs and modes; the eye hides the value; range is shared', async () => {
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-perf-big').textContent).toBe('+$142.10'));
    fireEvent.click(screen.getByTestId('account-perf-mode-value'));
    expect(screen.getByTestId('account-perf-big').textContent).toBe('$100,142.10');
    fireEvent.click(screen.getByTestId('account-perf-mode-pct'));
    expect(screen.getByTestId('account-perf-big').textContent).toBe('+0.14%');
    fireEvent.click(screen.getByTestId('account-perf-tab-symbol'));
    expect(screen.getByTestId('account-symbol-row-GRML').textContent).toContain('+$125.00');
    fireEvent.click(screen.getByTestId('account-perf-tab-source'));
    expect(screen.getByTestId('account-source-manual')).toBeTruthy();
    // The retired Phase D executor's Auto Paper card is gone unless old fills carry it (ADR 025).
    expect(screen.queryByTestId('account-source-auto_paper')).toBeNull();
    fireEvent.click(screen.getByTestId('account-eye'));
    expect(screen.getByTestId('account-tav').textContent).toBe('$•••,•••.••');
    fireEvent.click(screen.getByTestId('account-range-1M'));
    await waitFor(() => expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('range=1M'))).toBe(true));
    expect(screen.getByTestId('account-perf-range-1M').getAttribute('aria-selected')).toBe('true');
  });

  it('Orders (Today) buckets Expired on its own and wears est on practice fills', async () => {
    mocks.ibkr.orders = [];
    mocks.ibkr.closedOrders = [ORDER, EXPIRED];
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-orders-table')).toBeTruthy());
    expect(screen.getByTestId('account-order-filter-expired').textContent).toBe('Expired1');
    expect(screen.getByTestId('account-order-filter-filled').textContent).toBe('Filled1');
    fireEvent.click(screen.getByTestId('account-order-filter-expired'));
    expect(screen.getByTestId('account-order-7').textContent).toContain('Expired');
    expect(screen.queryByTestId('account-order-6')).toBeNull();
    fireEvent.click(screen.getByTestId('account-order-filter-all'));
    expect(screen.getByTestId('account-order-6').querySelector('[data-testid="acct-est"]')).toBeTruthy();
  });

  it('reset confirms, POSTs /api/practice/reset and refetches the history', async () => {
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-reset-button')).toBeTruthy());
    const before = mocks.fetch.mock.calls.filter((c) => String(c[0]).includes('/api/practice/history')).length;
    await act(async () => { fireEvent.click(screen.getByTestId('account-reset-button')); });
    expect(mocks.confirm).toHaveBeenCalledTimes(1);
    const dialog = mocks.confirm.mock.calls[0][0] as { title: string; message: string };
    expect(dialog.title).toMatch(/Paper practice account/);
    expect(dialog.message).toMatch(/archives the old ledger/);
    await waitFor(() => expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/api/practice/reset'))).toBe(true));
    await waitFor(() => expect(screen.getByTestId('account-reset-notice').textContent).toContain('$100,000.00'));
    await waitFor(() => {
      const after = mocks.fetch.mock.calls.filter((c) => String(c[0]).includes('/api/practice/history')).length;
      expect(after).toBeGreaterThan(before);
    });
  });

  it('a cancelled reset sends nothing', async () => {
    mocks.confirm.mockResolvedValue(false);
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-reset-button')).toBeTruthy());
    await act(async () => { fireEvent.click(screen.getByTestId('account-reset-button')); });
    expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('/api/practice/reset'))).toBe(false);
  });

  it('on Live shows the IBKR snapshot and states the absence of a practice ledger everywhere else', async () => {
    mocks.workspace.ibkrMode = 'live';
    mocks.ibkr.summary = {
      connected: true, mode: 'live', NetLiquidation: 25000, TotalCashValue: 20000, BuyingPower: 80000,
      ExcessLiquidity: 19000, RealizedPnL: 12, UnrealizedPnL: -3, GrossPositionValue: 5000,
    };
    render(<AccountPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('account-page').getAttribute('data-venue')).toBe('live');
    expect(screen.getByTestId('account-tav').textContent).toBe('$25,000.00');
    expect(screen.getByTestId('account-details-tag').textContent).toBe('IBKR');
    expect(screen.getByTestId('account-rows').textContent).toContain('$19,000.00');
    expect(screen.getByTestId('account-equity-absent').textContent).toBe(ACCOUNT_LIVE_NO_LEDGER);
    expect(screen.getByTestId('account-performance-absent').textContent).toBe(ACCOUNT_LIVE_NO_LEDGER);
    expect(screen.getByTestId('account-components-absent').textContent).toBe(ACCOUNT_LIVE_NO_LEDGER);
    expect(screen.getByTestId('account-calendar-absent').textContent).toBe(ACCOUNT_LIVE_NO_LEDGER);
    expect(screen.getByTestId('account-ledger-absent').textContent).toBe(ACCOUNT_LIVE_NO_LEDGER);
    expect(screen.queryByTestId('account-reset-bar')).toBeNull();
    expect(screen.queryByTestId('account-equity-curve')).toBeNull();
    await act(async () => { await Promise.resolve(); });
    expect(mocks.fetch).not.toHaveBeenCalled();
    // The old Account tab module stays reachable as Broker snapshot; Reports is a tab too.
    fireEvent.click(screen.getByTestId('account-page-tab-broker'));
    await waitFor(() => expect(screen.getByTestId('legacy-trading-tab').getAttribute('data-section')).toBe('overview'));
    fireEvent.click(screen.getByTestId('account-page-tab-reports'));
    await waitFor(() => expect(screen.getByTestId('legacy-trading-tab').getAttribute('data-section')).toBe('reports'));
  });

  it('hosts no second order ticket or Level 2 book under Reports or Broker snapshot (V23)', async () => {
    mocks.workspace.ibkrMode = 'live';
    render(<AccountPage onOpenTrader={() => {}} />);
    fireEvent.click(screen.getByTestId('account-page-tab-reports'));
    const reports = await screen.findByTestId('legacy-trading-tab');
    expect(reports.getAttribute('data-sections')).toBe('reports,activity,latency');
    expect(reports.getAttribute('data-ticket')).toBe('off');
    fireEvent.click(screen.getByTestId('account-page-tab-broker'));
    await waitFor(() => expect(screen.getByTestId('legacy-trading-tab').getAttribute('data-sections')).toBe('overview'));
    expect(screen.getByTestId('legacy-trading-tab').getAttribute('data-ticket')).toBe('off');
  });

  it('with no bot session the order size is unavailable, never the product ceiling (C35)', async () => {
    mocks.workspace.ibkrMode = 'live';
    mocks.bot.session = null;
    render(<AccountPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('account-bot-order-size').textContent).toMatch(/unavailable/);
    expect(screen.getByTestId('account-bot-order-size').textContent).not.toMatch(/10 sh/);
  });

  it('shows the bot cap as the size of each bot order and the largest position as every source\'s (W11)', async () => {
    mocks.bot.session = { caps: { max_shares: 1 }, soft_breaker_fired: false, day_lock_active: false };
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-largest-position').textContent).toBe('400 sh GRML · every source'));
    expect(screen.getByTestId('account-bot-order-size').textContent).toBe('1 sh per bot order');
    // Nothing reads "400 / 1 sh": the two figures are not compared.
    expect(screen.getByTestId('account-risk').textContent).not.toMatch(/\/ 1 sh/);
  });

  it('the Performance headline adds the live open P&L, agreeing with Day\'s P&L (W1)', async () => {
    // The history prices GRML at its last fill (event-marked open 12.00); the account marks it live (55.00).
    mocks.fetch.mockImplementation(async (url: string) => {
      const u = String(url);
      if (u.includes('/api/practice/history')) {
        const h = paperHistoryFixture();
        return { ok: true, status: 200, json: async () => ({ ...h, components: { ...h.components, unrealized: 12 } }) };
      }
      if (u.includes('/api/practice/account')) return { ok: true, status: 200, json: async () => PAPER_ACCOUNT_TODAY };
      return { ok: false, status: 404, json: async () => ({}) };
    });
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-perf-big').textContent).toBe('+$142.10'));
    expect(screen.getByTestId('account-day-line').textContent).toContain('+$142.10');
    expect(screen.getByTestId('account-comp-unrealized').textContent).toContain('+$55.00');
  });

  it('the calendar shows the whole month whatever the range (W5)', async () => {
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-calendar-grid')).toBeTruthy());
    expect(mocks.fetch.mock.calls.some((c) => String(c[0]).includes('range=ALL'))).toBe(true);
    expect(screen.getByTestId('account-calendar-foot').textContent).toContain('blank = no fills');
  });

  it('Orders name each row\'s own source stamp, never a blanket "Nova" (W9)', async () => {
    mocks.ibkr.orders = [{
      order_id: 9, symbol: 'GRML', side: 'BUY', qty: 1, order_type: 'LMT', limit_price: 8, status: 'Submitted',
      source: 'nova', order_source: 'manual', bot_id: null, submitted_at: new Date().toISOString(),
    }];
    mocks.ibkr.closedOrders = [{
      order_id: 10, symbol: 'GRML', side: 'SELL', qty: 1, order_type: 'MKT', limit_price: null, status: 'Filled',
      filled_qty: 1, avg_fill_price: 9, source: 'nova', order_source: 'bot', bot_id: 'hod-momo-1',
      filled_at: new Date().toISOString(),
    }];
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-order-source-9').textContent).toBe('Manual'));
    expect(screen.getByTestId('account-order-source-10').textContent).toBe('Bot · hod-momo-1');
  });

  it('on Live the Fills tab and commissions read IBKR\'s filled orders (W17), and Day\'s P&L says what it counts (W18)', async () => {
    mocks.workspace.ibkrMode = 'live';
    mocks.ibkr.summary = { connected: true, mode: 'live', NetLiquidation: 25000, RealizedPnL: 12, UnrealizedPnL: -3 };
    const filledOrder = (order_id: number, commission: number): IbkrOrder => ({
      order_id, perm_id: 100 + order_id, symbol: 'TOPS', side: 'BUY', qty: 100, filled_qty: 100, order_type: 'MKT',
      limit_price: null, avg_fill_price: 1.49, status: 'Filled', commission, source: 'nova',
      filled_at: new Date().toISOString(),
    });
    mocks.ibkr.closedOrders = [filledOrder(1, 7.5), filledOrder(2, 1.5)];
    render(<AccountPage onOpenTrader={() => {}} />);
    expect(screen.getByTestId('account-rows').textContent).toContain('-$9.00');
    fireEvent.click(screen.getByTestId('account-pos-tab-fills'));
    expect(screen.getAllByTestId(/account-fill-/)).toHaveLength(2);
    expect(screen.getByTestId('account-fills-table').querySelector('[data-testid="acct-est"]')).toBeNull();
    expect(screen.getByTestId('account-day-pnl-live-note').textContent).toMatch(/carried overnight/);
  });

  it('on the sample desk shows the sample account, polls no ledger and offers only Overview (V4)', async () => {
    window.history.replaceState({}, '', '/?view=sample');
    try {
      mocks.workspace.ibkrMode = 'paper';
      mocks.ibkr.summary = { connected: true, mode: 'paper', NetLiquidation: 100000, TotalCashValue: 99150 };
      render(<AccountPage onOpenTrader={() => {}} />);
      await act(async () => { await Promise.resolve(); });
      expect(screen.getByTestId('account-page-venue').textContent).toBe('Nova Marketing Sample Data');
      expect(screen.getByTestId('account-tav').textContent).toBe('$100,000.00');
      expect(screen.queryByTestId('account-page-tab-reports')).toBeNull();
      expect(screen.queryByTestId('account-page-tab-broker')).toBeNull();
      expect(screen.getByTestId('account-performance-absent').textContent).toMatch(/sample desk has no ledger history/);
      expect(mocks.fetch).not.toHaveBeenCalled();
    } finally {
      window.history.replaceState({}, '', '/');
    }
  });
});
