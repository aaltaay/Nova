/**
 * The Sim scratch account's day is the replay playhead's (QA 2026-09-22,
 * C20 / V32), and with nothing loaded off the live edge the page says so
 * instead of drawing an empty ledger (C69).
 *
 * @vitest-environment jsdom
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PAPER_ACCOUNT_TODAY, paperHistoryFixture } from '../account/accountFixtures';
import { resetAccountHistoryResourcesForTests } from '../account/accountHistoryResource';
import type { IbkrAccountSummary, IbkrOrder } from '../ibkr/types';
import { AccountPage } from './AccountPage';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  clock: {} as Record<string, unknown>,
  workspace: { ibkrMode: 'sim' as string, selectedSymbol: null as string | null, setSelectedSymbol: vi.fn(), ibkrConnected: true },
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
}));

vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('../ux', () => ({ confirmApp: vi.fn() }));
vi.mock('../workspace/WorkspaceContext', () => ({ useWorkspace: () => mocks.workspace }));
vi.mock('../ibkr/IbkrAccountContext', () => ({
  useIbkrAccountContext: () => mocks.ibkr,
  useOptionalIbkrAccountContext: () => mocks.ibkr,
}));
vi.mock('../bot/useBotSession', () => ({ useBotSession: () => ({ session: null }) }));
vi.mock('../ibkr/TradingTab', () => ({ TradingTab: () => <div data-testid="legacy-trading-tab" /> }));

// The replay playhead: Fri 2026-09-18 10:00 ET -- days before the browser's clock.
const PLAYHEAD = Date.parse('2026-09-18T10:00:00-04:00') / 1000;
const SIM_ACCOUNT = { ...PAPER_ACCOUNT_TODAY, venue: 'sim', account_id: 'NOVA-SIM', replay_key: ['historical', 'GRML', '2026-09-18', '09:15', '11:30'] };

let history: unknown = null;

beforeEach(() => {
  resetAccountHistoryResourcesForTests();
  mocks.fetch.mockReset();
  mocks.workspace.ibkrMode = 'sim';
  history = { ...paperHistoryFixture(PLAYHEAD), venue: 'sim', account_id: 'NOVA-SIM', archives: [] };
  mocks.clock = {
    sim: true, sim_time_et: '2026-09-18T10:00:00-04:00', session_date: '2026-09-18', live_edge: false,
    replay_source: 'historical', replay_symbol: 'GRML', replay_date: '2026-09-18',
  };
  mocks.fetch.mockImplementation(async (url: string) => {
    const u = String(url);
    if (u.includes('/api/sim/clock')) return { ok: true, status: 200, json: async () => mocks.clock };
    if (u.includes('/api/practice/history')) return { ok: true, status: 200, json: async () => history };
    if (u.includes('/api/practice/account')) return { ok: true, status: 200, json: async () => SIM_ACCOUNT };
    return { ok: false, status: 404, json: async () => ({}) };
  });
});

afterEach(cleanup);

describe('AccountPage on Sim', () => {
  it("takes today from the replay playhead: the playhead's day is outlined and its row reconciles (C20 / V32)", async () => {
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-calendar-day-2026-09-18').className).toMatch(/is-today/));
    await waitFor(() => expect(screen.getByTestId('account-rows-reconcile').getAttribute('data-reconcile')).toBe('ok'));
  });

  it('with nothing loaded off the live edge, the panels say so instead of "No fills in this range" (C69)', async () => {
    mocks.clock = { sim: true, sim_time_et: '2026-09-22T04:00:00-04:00', live_edge: false, replay_source: 'none' };
    history = { ...(history as object), fills: [], equity: [], daily: [], by_source: [] };
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-ledger-absent').textContent).toMatch(/^Sim: nothing loaded/));
    expect(screen.getByTestId('account-performance-absent').textContent).toMatch(/^Sim: nothing loaded/);
  });

  it('at the live edge nothing loaded is a live desk, not an absence', async () => {
    mocks.clock = { sim: true, sim_time_et: '2026-09-22T10:00:00-04:00', live_edge: true, replay_source: 'none' };
    history = { ...(history as object), fills: [], equity: [], daily: [], by_source: [] };
    render(<AccountPage onOpenTrader={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('account-ledger-table')).toBeTruthy());
    expect(screen.queryByTestId('account-ledger-absent')).toBeNull();
  });
});
