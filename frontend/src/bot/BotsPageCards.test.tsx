/**
 * @vitest-environment jsdom
 *
 * The Bots page cards (approved mockup v4): every control is a real one --
 * setup and level switches, the add-a-setup door, Level 2 links, sliders that
 * save once let go, proposals, the timeline and today's numbers.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOTS_CATALOGUE_PATH } from '../constantGroups/bots_page';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import type { SetupsBoard } from '../setups/types';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import { botsFetchRouter, gates, session, setupRow, type BotsFetchOpts } from './botsPageFixtures';

const ibkrStatus = { connected: true, spend_status: 'paper_armed', spend_locked_reason: null, trading_allowed: true, trading_allowed_reason: null, armed: true };
vi.mock('../ibkr/useIbkrStatus', () => ({ useIbkrStatus: () => ibkrStatus }));
// The padlock is the backend latch (ADR 018): this status's `armed` is the one answer.
vi.mock('../ibkr/ticketUnlock', () => ({
  readTicketSessionUnlocked: () => ibkrStatus.armed === true,
  subscribeTicketSessionUnlock: () => () => {},
  unlockNeedsPin: () => true,
  livePinMissing: () => false,
  unlockTicketSession: async () => ({ ok: true, code: null, message: null }),
  lockTicketSession: async () => ({ ok: true, code: null, message: null }),
}));
const openStockView = vi.fn();
vi.mock('../workspace/WorkspaceContext', () => ({
  useWorkspace: () => ({ openStockView, traderLiveTabs: ['GRML'], selectedSymbol: 'GRML', ibkrMode: 'paper' }),
}));
const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));
const setups: { board: SetupsBoard | null; connected: boolean } = { board: null, connected: true };
vi.mock('../setups/SetupsStreamContext', () => ({ useSetupsBoard: () => setups }));

const NOW = Date.now() / 1000;

function board(partial: Partial<SetupsBoard> = {}): SetupsBoard {
  return {
    schema_version: 1, generated_at: NOW, session_date: '2026-09-22', universe: 40, seeding: 0,
    scoreboard: true, scoreboard_error: null, proposing: true,
    rows: [
      { symbol: 'GRML', state: 'near', reason: '', kind: 'first_pullback', nth: 1, setup_id: 'g1',
        setup: { trigger: 8.72, entry: 8.73, stop: 8.52, risk: 0.21, target1: 8.92, pullback_bars: 2, leg_high: 8.9,
          leg_low: 8.2, leg_pct: 0.074 },
        leg: null, last_price: 8.69, distance: 0.03, grade: 'A', pillars: null, tape: null, proposal: null,
        outcome: null, bar_r: null, mfe: null, mae: null },
      { symbol: 'IMCC', state: 'leg', reason: '', kind: null, nth: 0, setup_id: null, setup: null,
        leg: { t: 0, high: 1.45, low: 1.35, pct: 0.074 }, last_price: 1.42, distance: null, grade: null,
        pillars: null, tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null },
    ],
    proposals: [
      { id: 'p-grml', setup_id: 'g1', symbol: 'GRML', kind: 'first_pullback', trigger: 8.72, entry: 8.73, stop: 8.52,
        target1: 8.92, risk: 0.21, grade: 'A', reasons: ['Level 2 bid stacking', 'tape buying at the ask'],
        created_at: NOW - 60, status: 'open', tape_now: 'go' },
    ],
    ...partial,
  };
}

beforeEach(() => {
  ibkrStatus.armed = true;
  setups.board = board();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  localStorage.clear();
  openStockView.mockReset();
  confirmApp.mockClear();
});

function mockFetch(opts: BotsFetchOpts = {}) {
  const fetchMock = vi.fn(botsFetchRouter(opts));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function flush() {
  for (let i = 0; i < 4; i += 1) await Promise.resolve();
}

async function renderPage() {
  await act(async () => {
    render(<BotsPage />);
    await flush();
  });
  await act(async () => { await flush(); });
}

function patches(fetchMock: ReturnType<typeof mockFetch>): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === 'PATCH')
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
}

describe('Strategies card', () => {
  it('shows the playbook: first pullback chosen with its rules and read-out, the rest waiting on scanners', async () => {
    mockFetch();
    await renderPage();
    const chosen = within(screen.getByTestId('bots-setup-first_pullback'));
    expect(chosen.getByText('First pullback')).toBeTruthy();
    expect(chosen.getByText(/Chosen/)).toBeTruthy();
    // The rules are the template in play's numbers in words (ADR 029), never hand-written prose.
    expect(chosen.getByText(/Leg ≥ 5% to a new high of day · 1–3 candles hold the 9 EMA/)).toBeTruthy();
    expect(chosen.getByText(/HOD Momo names · any price · any float/)).toBeTruthy();
    expect(chosen.getByText(/arms 07:00–11:30 · only when the tape says GO/)).toBeTruthy();
    expect(chosen.getByText(/bot 07:00–10:00, 1 a day/)).toBeTruthy();
    expect(chosen.getByText(/25k\+ seller not thinning/)).toBeTruthy();
    expect((screen.getByTestId('bots-setup-template-first_pullback') as HTMLSelectElement).value).toBe('default');
    expect(screen.getByTestId('bots-readout-count').textContent).toBe('12 / 50');
    expect(screen.getByTestId('bots-readout').textContent).toMatch(/GO so far \+0\.31R vs blind \/ wait −0\.18R/);
    for (const id of ['gap_and_go', 'flat_top_breakout', 'red_to_green', 'micro_pullback']) {
      const card = within(screen.getByTestId(`bots-setup-${id}`));
      expect(card.getByText(/No scanner yet/)).toBeTruthy();
      const radio = screen.getByTestId(`bots-setup-radio-${id}`) as HTMLInputElement;
      expect(radio.disabled).toBe(true);
      expect(radio.getAttribute('data-why')).toMatch(/No scanner yet/);
      const lvl = screen.getByTestId(`bots-setup-level-${id}-2`) as HTMLButtonElement;
      expect(lvl.disabled).toBe(true);
      expect(lvl.getAttribute('data-why')).toMatch(/No scanner yet/);
    }
    expect(within(screen.getByTestId('bots-setup-gap_and_go')).getByText('Bars alone: failed')).toBeTruthy();
    expect(within(screen.getByTestId('bots-setup-gap_and_go')).getByText(/Buy stop at the pre-market high until 10:00/))
      .toBeTruthy();
    const micro = screen.getByTestId('bots-setup-params-micro_pullback') as HTMLButtonElement;
    expect(micro.disabled).toBe(true);
    expect(micro.getAttribute('data-why')).toMatch(/never been tested/);
    expect(screen.queryByText(/Halt \/ LULD|Quote spike|Volume boost|LLM decide/)).toBeNull();
  });

  it('the chosen setup\'s own level switch sets the bot level', async () => {
    const fetchMock = mockFetch({ onPatch: body => session({ level: Number(body.level ?? 1) as 0 | 1 | 2 }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-setup-level-first_pullback-0')); await flush(); });
    expect(patches(fetchMock)).toContainEqual({ level: 0 });
    expect(screen.getByTestId('bots-setup-level-first_pullback-0').getAttribute('aria-checked')).toBe('true');
  });

  it('+ Add a setup explains what adding one takes and copies the catalogue path', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    mockFetch();
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-add-setup')); await flush(); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(writeText).toHaveBeenCalledWith(BOTS_CATALOGUE_PATH);
  });
});

describe('Symbols card', () => {
  it('says who holds each Level 2 line and opens a missing one pinned', async () => {
    mockFetch();
    await renderPage();
    expect(within(screen.getByTestId('bots-symbol-GRML')).getByText('Held · Trader')).toBeTruthy();
    fireEvent.click(screen.getByTestId('bots-symbol-open-l2-IMCC'));
    expect(openStockView).toHaveBeenCalledWith('IMCC', { pin: true });
    // Last from the setup scanner; its first-pullback state beside it.
    const grml = within(screen.getByTestId('bots-symbol-GRML'));
    expect(grml.getByText('8.69')).toBeTruthy();
    expect(grml.getByText('Near · 8.72')).toBeTruthy();
    expect(within(screen.getByTestId('bots-symbol-IMCC')).getByText('Leg +7.4%')).toBeTruthy();
  });

  it('adds (upper-cased) and removes symbols through POST /bot/allowlist', async () => {
    const ops: Array<{ symbol: string; op: string }> = [];
    let list = ['GRML', 'IMCC'];
    mockFetch({ onAllowlist: body => {
      ops.push(body);
      list = body.op === 'remove' ? list.filter(s => s !== body.symbol) : [...list, body.symbol];
      return session({ symbol_allowlist: list });
    } });
    await renderPage();
    await act(async () => {
      fireEvent.change(screen.getByTestId('bots-symbol-input'), { target: { value: 'efgh' } });
      fireEvent.click(screen.getByTestId('bots-symbol-add'));
      await flush();
    });
    expect(ops).toContainEqual({ symbol: 'EFGH', op: 'add' });
    expect((screen.getByTestId('bots-symbol-input') as HTMLInputElement).value).toBe('');
    await act(async () => { fireEvent.click(screen.getByTestId('bots-symbol-remove-IMCC')); await flush(); });
    expect(ops).toContainEqual({ symbol: 'IMCC', op: 'remove' });
  });
});

describe('Risk sleeve', () => {
  it('PATCHes a slider once it is let go, not once per step', async () => {
    const fetchMock = mockFetch({ onPatch: () => session() });
    await renderPage();
    const shares = screen.getByTestId('bot-strategy-max-shares');
    await act(async () => {
      fireEvent.change(shares, { target: { value: '3' } });
      fireEvent.change(shares, { target: { value: '4' } });
      fireEvent.pointerUp(shares);
      await flush();
    });
    expect(patches(fetchMock)).toEqual([{ caps: { max_shares: 4 } }]);
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-bp-budget'), { target: { value: '25' } });
      fireEvent.blur(screen.getByTestId('bot-strategy-bp-budget'));
      fireEvent.click(screen.getByTestId('bot-strategy-eh'));
      await flush();
    });
    expect(patches(fetchMock)).toEqual(expect.arrayContaining([
      { caps: { bp_budget_usd: 25 } },
      { caps: { extended_hours: true } },
    ]));
  });

  it('draws both locked breakers and today\'s P&L on one scale', async () => {
    mockFetch({ dayPnl: -9.54 });
    await renderPage();
    const breakers = screen.getByTestId('bot-strategy-breakers').textContent ?? '';
    expect(breakers).toMatch(/locked/);
    expect(breakers).toMatch(/−\$200 all-stop · day lock/);
    expect(breakers).toMatch(/−\$50 bot trip/);
    expect(screen.getByTestId('bots-breaker-today').textContent).toBe('−$9.54 today');
    expect((screen.getByTestId('bots-breaker-now') as HTMLElement).style.left).toBe('95.23%');
  });
});

describe('Proposals, activity and today', () => {
  it('keeps the open setup proposal with its distance, reasons and reward / risk; Stage opens pinned', async () => {
    mockFetch();
    await renderPage();
    const card = within(screen.getByTestId('bots-setup-proposal-GRML'));
    expect(card.getByText(/0\.03 under the trigger · Level 2 bid stacking, tape buying at the ask · 20¢ \/ 20¢/)).toBeTruthy();
    expect(screen.getByTestId('bots-proposals-count').textContent).toBe('1 open');
    await act(async () => { fireEvent.click(screen.getByTestId('bots-stage-GRML')); await flush(); });
    expect(openStockView).toHaveBeenCalledWith('GRML', { pin: true });
    expect(screen.queryByTestId('bots-setup-proposal-GRML')).toBeNull();
  });

  it('lists a proposal the scanner withdrew, from the audit stream', async () => {
    mockFetch({ audit: [{
      timestamp: NOW - 120, level: 2, strategy: null, brain_session_id: null, action: 'setup_proposal',
      inputs: { id: 'p-imcc', symbol: 'IMCC', kind: 'first_pullback', trigger: 1.45, stop: 1.39, closed_at: NOW - 120 },
      reason: 're-armed at new levels -- the next go raises a fresh one', order_id: null, advise_spend: null,
      outcome: 'rearmed',
    }] });
    await renderPage();
    const card = within(screen.getByTestId('bots-closed-proposal-IMCC'));
    expect(card.getByText(/withdrawn/)).toBeTruthy();
    expect(card.getByText(/Re-armed at new levels/)).toBeTruthy();
  });

  it('keeps bot proposals in the inbox; Mark accepted never places', async () => {
    const fetchMock = mockFetch({ proposals: [{
      id: 'p1', symbol: 'GRML', side: 'BUY', kind: 'buy_limit_ask_offset', shortcut: 'buy_limit_ask_offset',
      preset_qty: 1, reason: 'first pullback near 8.72, tape go', confidence: null, status: 'pending',
    }] });
    await renderPage();
    const card = within(screen.getByTestId('bots-bot-proposal-p1'));
    await act(async () => { fireEvent.click(card.getByText('Mark accepted')); await flush(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/proposals/p1/accept'))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/bot/action'))).toBe(false);
  });

  it('draws the day\'s timeline from the audit stream and the setup scanner, and filters it', async () => {
    mockFetch({
      audit: [
        { timestamp: 1_790_000_300, level: 1, strategy: null, brain_session_id: null, action: 'level',
          inputs: { from: 1, to: 2 }, reason: null, order_id: null, advise_spend: null, outcome: '1->2' },
        { timestamp: 1_790_000_400, level: 2, strategy: null, brain_session_id: null, action: 'setup_proposal',
          inputs: { symbol: 'GRML', kind: 'first_pullback', tape_now: 'go', grade: 'A' }, reason: null, order_id: null,
          advise_spend: null, outcome: 'proposed' },
      ],
      setupRows: [
        setupRow({ armed_at: 1_790_000_100 }),
        setupRow({ id: 'IMCC-1', symbol: 'IMCC', trigger: 1.45, stop: 1.39, pullback_bars: 1, leg_pct: 0.05, grade: 'B',
          armed_at: 1_790_000_050, near_at: 1_790_000_200,
          near_tape: { verdict: 'wait', reasons: ['25k seller at the level, not thinning'] } }),
      ],
    });
    await renderPage();
    const activity = within(screen.getByTestId('bots-activity'));
    expect(activity.getByText('Level Eyes → Strategy')).toBeTruthy();
    expect(activity.getByText('Proposed GRML first pullback')).toBeTruthy();
    expect(activity.getByText('tape go · grade A')).toBeTruthy();
    expect(activity.getByText('Armed GRML · trigger 8.72 · stop 8.52')).toBeTruthy();
    expect(activity.getByText('2 red candles held the 9 EMA · leg +7.4% · grade A')).toBeTruthy();
    expect(activity.getByText('Wait IMCC near 1.45')).toBeTruthy();
    await act(async () => { fireEvent.click(activity.getByText('Proposals')); });
    expect(activity.queryByText('Level Eyes → Strategy')).toBeNull();
    expect(activity.queryByText('Armed GRML · trigger 8.72 · stop 8.52')).toBeNull();
    expect(activity.getByText('Proposed GRML first pullback')).toBeTruthy();
  });

  it('counts today and scores the tape splits', async () => {
    mockFetch();
    await renderPage();
    expect(screen.getByTestId('bots-kpi-armed').textContent).toBe('6');
    expect(screen.getByTestId('bots-kpi-triggered').textContent).toBe('2');
    const table = within(screen.getByTestId('bots-scoreboard'));
    expect(table.getByText('GO')).toBeTruthy();
    expect(table.getByText('+0.31R')).toBeTruthy();
    expect(table.getByText('−0.24R')).toBeTruthy();
    // Paper with no ledger answer yet: the bot's P&L is unknown, never $0.
    expect(screen.getByTestId('bots-kpi-pnl').textContent).toBe('—');
  });

  it('states the bot footer: working orders and the kinds it may send', async () => {
    mockFetch({ session: session({ gates: gates(), caps: {
      max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: ['buy_market', 'exit_pos'],
    } }) });
    await renderPage();
    const footer = screen.getByTestId('bots-status').textContent ?? '';
    expect(footer).toMatch(/GRML · flat · 0 bot working orders/);
    expect(footer).toMatch(/Order kinds the bot may send: buy_market · exit_pos/);
  });
});
