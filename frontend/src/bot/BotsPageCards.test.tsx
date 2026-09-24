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
import { consumeSetupsBoardOpen, getSetupsFilter } from '../setups';
import type { SetupCounts, SetupsBoard, SetupSummary } from '../setups/types';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import { botsFetchRouter, breakers, gates, session, setupRow, type BotsFetchOpts } from './botsPageFixtures';

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

const counts = (partial: Partial<SetupCounts> = {}): SetupCounts => ({
  watching: 40, forming: 1, armed: 2, near: 1, triggered: 0, failed: 0, filtered: 0, proposed: 1, ...partial,
});

const summary = (id: string, partial: Partial<SetupSummary> = {}): SetupSummary => ({
  id, level: 0, chosen: false, proposing: false, template: { id: 'default', rev: 1, name: 'Default (pre-registered)' },
  templates_watched: 1, window: { start: '07:00', end: '11:30', state: 'open' }, counts: counts({ armed: 0, near: 0,
    forming: 0, proposed: 0 }), ...partial,
});

function board(partial: Partial<SetupsBoard> = {}): SetupsBoard {
  return {
    schema_version: 2, generated_at: NOW, session_date: '2026-09-22', universe: 40, seeding: 2,
    scoreboard: true, scoreboard_error: null, proposing: true,
    setups: [
      summary('first_pullback', { level: 1, chosen: true, proposing: true, counts: counts() }),
      summary('bull_flag', { counts: counts({ armed: 1, near: 0, forming: 0, proposed: 0 }) }),
      summary('flat_top_breakout'),
      summary('red_to_green', { window: { start: '09:30', end: '10:30', state: 'before' } }),
    ],
    rows: [
      { symbol: 'GRML', setup_type: 'first_pullback', state: 'near', reason: '0.03 under the 8.72 trigger -- read the tape',
        kind: 'first_pullback', nth: 1, setup_id: 'g1',
        setup: { trigger: 8.72, entry: 8.73, stop: 8.52, risk: 0.21, target1: 8.92, pullback_bars: 2, leg_high: 8.9,
          leg_low: 8.2, leg_pct: 0.074 },
        leg: null, last_price: 8.69, distance: 0.03, grade: 'A', pillars: null,
        tape: { verdict: 'go', reasons: ['green on the tape (5 prints, 2.4k at the ask)'],
          metrics: { best_bid: 8.68, best_ask: 8.69, spread: 0.01, ask_prints: 5, bid_prints: 1, ask_volume: 2400,
            bid_volume: 300, window_sec: 10 } },
        proposal: null, outcome: null, bar_r: null, mfe: null, mae: null },
      { symbol: 'GRML', setup_type: 'bull_flag', state: 'armed', reason: 'flag of 2 under the 8.90 pole: trigger 8.75',
        kind: 'bull_flag', nth: 0, setup_id: 'g2@bull_flag',
        setup: { trigger: 8.75, entry: 8.76, stop: 8.55, risk: 0.21, target1: 9.18, pullback_bars: 2, leg_high: 8.9,
          leg_low: 8.2, leg_pct: 0.085, detail: { pole_bars: 3, flag_bars: 2 } },
        leg: { t: 0, high: 8.9, low: 8.2, pct: 0.085, bars: 3 }, last_price: 8.69, distance: 0.06, grade: 'B',
        pillars: null, tape: null, proposal: null, outcome: null, bar_r: null, mfe: null, mae: null },
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
  it('shows the playbook: first pullback chosen with its rules, tape gate and read-out; every setup its own card', async () => {
    mockFetch();
    await renderPage();
    const chosen = within(screen.getByTestId('bots-setup-first_pullback'));
    expect(chosen.getByText('First pullback')).toBeTruthy();
    expect(chosen.getByText(/Chosen/)).toBeTruthy();
    // The rules are the template in play's numbers in words (ADR 029): a line on the card, all of it on hover.
    const rules = screen.getByTestId('bots-setup-rules-first_pullback');
    expect(rules.textContent).toBe('Leg ≥ 5% · 1–3 bar pullback · stop at the pullback low');
    const tip = rules.getAttribute('data-tip') ?? '';
    expect(tip).toMatch(/Leg ≥ 5% to a new high of day · 1–3 candles hold the 9 EMA/);
    expect(tip).toMatch(/HOD Momo names · any price · any float/);
    expect(tip).toMatch(/arms 07:00–11:30 · only when the tape says GO/);
    expect(tip).toMatch(/bot 07:00–10:00, 1 a day/);
    expect(chosen.getByText(/25k\+ seller not thinning/)).toBeTruthy();
    expect((screen.getByTestId('bots-setup-template-first_pullback') as HTMLSelectElement).value).toBe('default');
    expect(screen.getByTestId('bots-readout-count').textContent).toBe('12 / 50');
    expect(screen.getByTestId('bots-readout').textContent).toMatch(/GO so far \+0\.31R vs blind \/ wait −0\.18R/);
    // ADR 031: the bull flag, flat-top and red to green have scanners: chosen by radio, Off or Eyes on their own card.
    for (const id of ['bull_flag', 'flat_top_breakout', 'red_to_green']) {
      expect((screen.getByTestId(`bots-setup-radio-${id}`) as HTMLInputElement).disabled).toBe(false);
      expect(screen.getByTestId(`bots-setup-level-${id}-0`).getAttribute('aria-checked')).toBe('true');
      expect((screen.getByTestId(`bots-setup-level-${id}-1`) as HTMLButtonElement).disabled).toBe(false);
      const strategy = screen.getByTestId(`bots-setup-level-${id}-2`) as HTMLButtonElement;
      expect(strategy.disabled).toBe(true);
      expect(strategy.getAttribute('data-why')).toMatch(/Only the chosen setup can be at Strategy/);
    }
    expect(screen.getByTestId('bots-setup-readout-bull_flag').textContent).toMatch(/Read-out.*0 \/ 50/);
    // Gap and Go and the micro pullback say what is missing and what unblocks it.
    for (const id of ['gap_and_go', 'micro_pullback']) {
      const radio = screen.getByTestId(`bots-setup-radio-${id}`) as HTMLInputElement;
      expect(radio.disabled).toBe(true);
      expect(radio.getAttribute('data-why')).toMatch(/No scanner yet/);
      expect(screen.getByTestId(`bots-noscan-${id}`).textContent).toMatch(/Why it can't watch yet\..*Unblocks when/);
    }
    expect(screen.getByTestId('bots-noscan-micro_pullback').textContent).toMatch(/one-second bars/);
    expect(within(screen.getByTestId('bots-setup-gap_and_go')).getByText('Bars alone: failed')).toBeTruthy();
    const micro = screen.getByTestId('bots-setup-params-micro_pullback') as HTMLButtonElement;
    expect(micro.disabled).toBe(true);
    expect(micro.getAttribute('data-why')).toMatch(/never been tested/);
    expect(screen.queryByText(/Halt \/ LULD|Quote spike|Volume boost|LLM decide/)).toBeNull();
  });

  it('each card carries its own small scanner, said in the setup\'s words, every chip explained on hover', async () => {
    mockFetch();
    await renderPage();
    const status = within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-status');
    expect(status.textContent).toMatch(/Watching 40 names · window 07:00–11:30 · 2 seeding bars/);
    expect(within(status).getByTestId('bots-setup-level-chip').textContent).toBe('Eyes · pings on near + go');
    expect(within(screen.getByTestId('bots-setup-bull_flag')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Off · scores silently');
    expect(within(screen.getByTestId('bots-setup-red_to_green')).getByTestId('bots-setup-status').textContent)
      .toMatch(/opens 09:30/);
    const state = screen.getByTestId('bots-scan-state-first_pullback-GRML');
    expect(state.textContent).toBe('Near');
    expect(state.getAttribute('data-tip-title')).toBe('Near · First pullback');
    expect(state.getAttribute('data-tip')).toMatch(/Price is a few cents under the trigger/);
    expect(state.getAttribute('data-tip')).toMatch(/Trigger 8\.72 · entry 8\.73 · stop 8\.52 · risk 21¢ a share · target 1 8\.92/);
    expect(state.getAttribute('data-tip')).toMatch(/Now: 0\.03 under the 8\.72 trigger — read the tape/);
    const tape = screen.getByTestId('bots-scan-tape-first_pullback-GRML');
    expect(tape.textContent).toBe('GO');
    expect(tape.getAttribute('data-tip')).toMatch(/^GO: green prints at the ask/);
    expect(tape.getAttribute('data-tip')).toMatch(/5 prints at the ask \(2\.4k\) vs 1 at the bid \(300\)/);
    // The bull flag's own words, and the tag naming the symbol's other setup.
    expect(screen.getByTestId('bots-scan-state-bull_flag-GRML').textContent).toBe('Flag · 2 bars');
    expect(within(screen.getByTestId('bots-scan-row-first_pullback-GRML')).getByText('+ bull flag')).toBeTruthy();
    expect(screen.getByTestId('bots-funnel-first_pullback').textContent)
      .toMatch(/Today\s*1 forming\s*→\s*2 armed\s*→\s*1 near\s*→\s*0 triggered\s*·\s*0 failed\s*·\s*1 proposed/);
    fireEvent.click(screen.getByTestId('bots-scan-row-first_pullback-GRML'));
    expect(openStockView).toHaveBeenCalledWith('GRML', { pin: true });
  });

  it('a setup\'s own Off / Eyes PATCHes its level; Open board asks for Watchlist › Setups filtered to it', async () => {
    const fetchMock = mockFetch({ onPatch: body => session({ setup_levels: { ...(body.setup_levels as object) } }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-setup-level-bull_flag-1')); await flush(); });
    expect(patches(fetchMock)).toContainEqual({ setup_levels: { bull_flag: 1 } });
    fireEvent.click(screen.getByTestId('bots-setup-board-red_to_green'));
    expect(getSetupsFilter()).toBe('red_to_green');
    expect(consumeSetupsBoardOpen()).toBe(true);
  });

  it('choosing another setup PATCHes the setup that plays', async () => {
    const fetchMock = mockFetch();
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-setup-radio-bull_flag')); await flush(); });
    expect(patches(fetchMock)).toContainEqual({ setup: 'bull_flag' });
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
    // Last from the setup scanner; a chip per setup it is on, most advanced first (ADR 031).
    const grml = within(screen.getByTestId('bots-symbol-GRML'));
    expect(grml.getByText('8.69')).toBeTruthy();
    expect(screen.getByTestId('bots-symbol-setup-GRML-first_pullback').textContent).toBe('First pullback · Near');
    expect(screen.getByTestId('bots-symbol-setup-GRML-bull_flag').textContent).toBe('Bull flag · Flag · 2 bars');
    expect(screen.getByTestId('bots-symbol-setup-IMCC-first_pullback').textContent).toBe('First pullback · Leg up +7.4%');
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

  it('draws the desk venue\'s breakers and today\'s P&L on one bar (ADR 032)', async () => {
    mockFetch({ dayPnl: -9.54 });
    await renderPage();
    const bar = screen.getByTestId('bot-strategy-breakers').textContent ?? '';
    expect(bar).toMatch(/Paper · drag to move · defaults/);
    expect(screen.getByTestId('bots-breaker-hard-label').textContent).toBe('−$200 all-stop');
    expect(screen.getByTestId('bots-breaker-soft-label').textContent).toBe('−$50 bot trip');
    expect(screen.getByTestId('bots-breaker-today').textContent).toBe('−$9.54 today');
    // The bar runs from −$250 (room past the all-stop) to $0.
    expect(parseFloat((screen.getByTestId('bots-breaker-now') as HTMLElement).style.left)).toBeCloseTo(96.184, 3);
    expect(parseFloat((screen.getByTestId('bots-breaker-soft') as HTMLElement).style.left)).toBeCloseTo(80, 6);
    const soft = screen.getByTestId('bots-breaker-soft');
    expect(soft.getAttribute('role')).toBe('slider');
    expect(soft.getAttribute('data-tip')).toMatch(/^Bot trip: when the whole account's day P&L/);
  });

  it('drags the bot trip and saves the venue\'s pair on release; a restart reads it back from the session', async () => {
    const fetchMock = mockFetch({ onPatch: body => {
      const b = body.breakers as { soft_usd: number };
      return session({ breakers: breakers({ soft_usd: b.soft_usd, custom: true }) });
    } });
    await renderPage();
    const bar = screen.getByTestId('bot-strategy-breakers').querySelector('.bots-breakers__bar') as HTMLElement;
    bar.getBoundingClientRect = () => ({ left: 0, width: 250, top: 0, height: 6, right: 250, bottom: 6, x: 0, y: 0,
      toJSON: () => ({}) }) as DOMRect;
    const soft = screen.getByTestId('bots-breaker-soft');
    await act(async () => {
      fireEvent.pointerDown(soft, { button: 0, clientX: 200, pointerId: 1 });
      fireEvent.pointerMove(soft, { clientX: 150, pointerId: 1 });
      fireEvent.pointerMove(soft, { clientX: 125, pointerId: 1 });
      fireEvent.pointerUp(soft, { clientX: 125, pointerId: 1 });
      await flush();
    });
    expect(patches(fetchMock)).toEqual([{ breakers: { venue: 'paper', soft_usd: -125 } }]);
    expect(screen.getByTestId('bots-breaker-soft-label').textContent).toBe('−$125 bot trip');
    expect(screen.getByTestId('bots-breakers-venue').textContent).toMatch(/Paper · drag to move · yours/);
    expect(confirmApp).not.toHaveBeenCalled();
  });

  it('asks before loosening Live, and keeps the old value when the answer is no', async () => {
    confirmApp.mockImplementationOnce(async () => false);
    const fetchMock = mockFetch({ session: session({ breakers: breakers({ venue: 'live' }) }) });
    await renderPage();
    const soft = screen.getByTestId('bots-breaker-soft');
    await act(async () => {
      soft.focus();
      fireEvent.keyDown(soft, { key: 'ArrowLeft' });
      fireEvent.blur(soft);
      await new Promise(r => setTimeout(r, 450));
      await flush();
    });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(String((confirmApp.mock.calls[0] as unknown[])[0] && JSON.stringify(confirmApp.mock.calls[0]))).toMatch(/Loosen Live/);
    expect(patches(fetchMock)).toEqual([]);
    expect(screen.getByTestId('bots-breaker-soft-label').textContent).toBe('−$50 bot trip');
  });

  it('an API older than ADR 032 keeps the fixed pair and says why the markers do not move', async () => {
    const old = session();
    delete old.breakers;
    mockFetch({ session: old });
    await renderPage();
    const soft = screen.getByTestId('bots-breaker-soft');
    expect(soft.getAttribute('aria-disabled')).toBe('true');
    expect(soft.getAttribute('data-why')).toMatch(/restart the backend to move them/);
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
    expect(activity.getByText('Armed GRML · First pullback · trigger 8.72 · stop 8.52')).toBeTruthy();
    expect(activity.getByText('2 red candles held the 9 EMA · leg +7.4% · grade A')).toBeTruthy();
    expect(activity.getByText('Wait IMCC near 1.45')).toBeTruthy();
    await act(async () => { fireEvent.click(activity.getByText('Proposals')); });
    expect(activity.queryByText('Level Eyes → Strategy')).toBeNull();
    expect(activity.queryByText('Armed GRML · First pullback · trigger 8.72 · stop 8.52')).toBeNull();
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
