/**
 * @vitest-environment jsdom
 *
 * The Bots page cards (ADR 044, approved mockup v8): every control is a real one -- each
 * strategy's own Off / Eyes / On and its bot rules, the add-a-setup door, IBKR's Level 2
 * lines and lending, Tickers today (the hot list, Buy / Sell per stock, the squares), the
 * sleeve per venue that saves once let go, the breakers' day, proposals that say who
 * takes them, the timeline and today's numbers.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOTS_CATALOGUE_PATH } from '../constantGroups/bots_page';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { consumeSetupsBoardOpen, getSetupsFilter } from '../setups';
import { _resetDismissedForTests } from '../setups/proposalDismissals';
import { _resetSleeveForTests } from '../setups/sleeveRisk';
import type { SetupCounts, SetupsBoard, SetupSummary } from '../setups/types';
import { resetHotListForTests } from '../hot_list';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import {
  botsFetchRouter, breakers, caps, hotListView, linesView, refusal, session, setupRow, strategySession, templatesPayload,
  type BotsFetchOpts,
} from './botsPageFixtures';

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
/** 2026-09-30 09:42 ET. */
const AT_0942 = Date.UTC(2026, 8, 30, 13, 42) / 1000;

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
      summary('first_pullback', { level: 1, proposing: true, counts: counts() }),
      summary('bull_flag', { level: 1, proposing: true, counts: counts({ armed: 1, near: 0, forming: 0, proposed: 0 }) }),
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
        proposal: null, outcome: null, bar_r: null, mfe: null, mae: null,
        tf5: { agrees: false, above_ema9: true, macd_up: false, close: 8.66, ema9: 8.6, macd_hist: -0.012, candles: 40,
          as_of: Date.UTC(2026, 8, 21, 13, 35) / 1000 },
        tf5_at: 'armed' },
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
  _resetDismissedForTests();   // one dismissed list with the alert card, held in memory between tests
  _resetSleeveForTests();
  resetHotListForTests();
});

afterEach(() => {
  cleanup();
  resetHotListForTests();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  localStorage.clear();
  sessionStorage.clear();
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

/** Every request to a path with one method: its url and body. */
function calls(fetchMock: ReturnType<typeof mockFetch>, part: string, method: string) {
  return fetchMock.mock.calls.filter(([url, init]) => String(url).includes(part) && (init as RequestInit | undefined)?.method === method)
    .map(([url, init]) => ({ url: String(url), body: String((init as RequestInit | undefined)?.body ?? '') }));
}

describe('Strategies card (ADR 044: Off / Eyes / On per strategy)', () => {
  it('gives every setup with a scanner its own Off / Eyes / On, and no chosen setup', async () => {
    mockFetch();
    await renderPage();
    expect(screen.queryByTestId('bots-setup-radio-first_pullback')).toBeNull();
    expect(screen.getByTestId('bots-strategies').textContent).not.toMatch(/Bot trades this|chosen/i);
    for (const id of ['first_pullback', 'bull_flag', 'flat_top_breakout', 'red_to_green']) {
      for (const n of [0, 1, 2]) {
        const btn = screen.getByTestId(`bots-setup-level-${id}-${n}`) as HTMLButtonElement;
        expect(btn.disabled).toBe(false);
        expect(btn.getAttribute('data-why')).toBeNull();
      }
    }
    // The card shows its own level, in the switch's words: Off, Eyes, On.
    expect(screen.getByTestId('bots-setup-level-first_pullback-2').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('bots-setup-level-first_pullback-2').textContent).toBe('On');
    expect(within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('On · alerts you while the Bot is off');
    expect(within(screen.getByTestId('bots-setup-bull_flag')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Eyes · alerts you');
    expect(within(screen.getByTestId('bots-setup-flat_top_breakout')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Off · silent');
  });

  it('draws each card\'s rules, tape gate and read-out, which unlocks nothing yet', async () => {
    mockFetch();
    await renderPage();
    const rules = screen.getByTestId('bots-setup-rules-first_pullback');
    expect(rules.textContent).toBe('Leg ≥ 5% · 1–3 bar pullback · stop at the pullback low');
    const tip = rules.getAttribute('data-tip') ?? '';
    expect(tip).toMatch(/arms 07:00–11:30 · only when the tape says GO/);
    expect(tip).toMatch(/bot 07:00–10:00/);
    expect(tip).not.toMatch(/a day/);
    expect(within(screen.getByTestId('bots-setup-red_to_green')).getByTestId('bots-setup-rules-red_to_green').getAttribute('data-tip'))
      .toMatch(/bot 09:30–10:00(?! \()/);   // red to green's built-in sits inside its 09:30-10:30 arming window
    for (const id of ['first_pullback', 'bull_flag']) {
      expect(within(screen.getByTestId(`bots-setup-${id}`)).getByText(/25k\+ seller not thinning/)).toBeTruthy();
    }
    const readout = screen.getByTestId('bots-setup-readout-first_pullback');
    expect(screen.getByTestId('bots-readout-count-first_pullback').textContent).toBe('12 / 50');
    expect(readout.textContent).toMatch(/GO so far \+0\.31R vs blind \/ wait −0\.41R/);
    expect(screen.getByTestId('bots-readout-inside-first_pullback').textContent)
      .toBe('19 triggered inside the bot window 07:00–10:00 (10 at GO)');
    expect(screen.getByTestId('bots-readout-what-first_pullback').textContent).toBe('Measures whether the tape gate turns this '
      + 'setup into a winner. Nova\'s bot trades Paper and Sim only; Live trading by a bot is not built, so passing it unlocks nothing yet.');
    expect(readout.textContent).toMatch(/scores the backtest's exit \(half at target 1, the stop to break-even, a 9 EMA trail\); the bot sells everything at target 1, with a 15-minute time stop/);
    const words = readout.getAttribute('data-tip') ?? '';
    expect(words).toMatch(/^Measures whether the tape gate turns this setup into a winner\./);
    expect(words).toMatch(/It counts every first pullback this template armed that triggered/);
    expect(screen.getByTestId('bots-strategies').textContent).not.toMatch(/100 Paper trades|unlock Strategy on Live/);
  });

  it('the setups without a scanner share one line, each saying on hover why it cannot watch yet', async () => {
    mockFetch();
    await renderPage();
    const line = screen.getByTestId('bots-noscan-line');
    expect(line.textContent).toMatch(/^Not watching yet: Gap and Go · Micro pullback\./);
    for (const id of ['gap_and_go', 'micro_pullback']) {
      expect(screen.queryByTestId(`bots-setup-${id}`)).toBeNull();
      expect(screen.queryByTestId(`bots-setup-level-${id}-0`)).toBeNull();
    }
    const micro = within(line).getByText('Micro pullback').parentElement;
    expect(micro?.getAttribute('data-tip')).toMatch(/one-second bars/);
    expect(micro?.getAttribute('data-tip')).toMatch(/Unblocks when:/);
    expect(screen.queryByText(/Halt \/ LULD|Quote spike|Volume boost|LLM decide/)).toBeNull();
  });

  it('a strategy at On alerts like Eyes while the Bot is off, and says so', async () => {
    mockFetch({ session: strategySession() });
    await renderPage();
    const chip = within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-level-chip');
    expect(chip.textContent).toBe('On · alerts you while the Bot is off');
    expect(chip.getAttribute('data-tip')).toMatch(/the Bot is off on this venue, so it alerts you like Eyes/);
    cleanup();
    _resetBotSessionPollerForTests();
    mockFetch({ session: strategySession({ bot_on: true, active: true }) });
    await renderPage();
    expect(within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('On · Nova may act on it');
  });

  it('each card carries its own small scanner, said in the setup\'s words, every chip explained on hover', async () => {
    mockFetch();
    await renderPage();
    const status = within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-status');
    expect(status.textContent).toMatch(/Watching 40 names · window 07:00–11:30 · 2 seeding bars/);
    expect(within(screen.getByTestId('bots-setup-red_to_green')).getByTestId('bots-setup-status').textContent)
      .toMatch(/opens 09:30/);
    const state = screen.getByTestId('bots-scan-state-first_pullback-GRML');
    expect(state.textContent).toBe('Near');
    expect(state.getAttribute('data-tip')).toMatch(/Trigger 8\.72 · entry 8\.73 · stop 8\.52 · risk 21¢ a share · target 1 8\.92/);
    expect(state.getAttribute('data-tip')).toMatch(/Now: 0\.03 under the 8\.72 trigger — read the tape/);
    const tape = screen.getByTestId('bots-scan-tape-first_pullback-GRML');
    expect(tape.textContent).toBe('GO');
    expect(tape.getAttribute('data-tip')).toMatch(/^GO: green prints at the ask/);
    expect(tape.getAttribute('data-tip')).toMatch(/5 prints at the ask \(2\.4k\) vs 1 at the bid \(300\)/);
    // The 5-minute chart's read (trial T8): shown, never a warning colour, explained on hover.
    const tf5 = screen.getByTestId('bots-scan-tf5-first_pullback-GRML');
    expect(tf5.textContent).toBe('5m ✗');
    expect(tf5.className).toContain('bots-tf5--against');
    expect(tf5.getAttribute('data-tip-title')).toBe('5-minute against');
    expect(tf5.getAttribute('data-tip')).toMatch(/Read when it armed, on the 09:35 5-minute candle: it closed over its 9 EMA \(8\.60\), and its MACD is down/);
    expect(tf5.getAttribute('data-tip')).toMatch(/In trial T8: shown only, it never blocks a trade/);
    // The bull flag's own words, and the tag naming the symbol's other setup.
    expect(screen.getByTestId('bots-scan-state-bull_flag-GRML').textContent).toBe('Flag · 2 bars');
    expect(screen.getByTestId('bots-funnel-first_pullback').textContent)
      .toMatch(/Today\s*1 forming\s*→\s*2 armed\s*→\s*1 near\s*→\s*0 triggered\s*·\s*0 failed\s*·\s*1 proposed/);
    fireEvent.click(screen.getByTestId('bots-scan-row-first_pullback-GRML'));
    expect(openStockView).toHaveBeenCalledWith('GRML', { pin: true });
  });

  it('in Sim off the live edge the cards are what Nova\'s eyes recorded at the playhead, and say so', async () => {
    const at = Date.UTC(2026, 8, 24, 12, 7, 2) / 1000;        // 08:07:02 ET
    setups.board = board({
      source: 'sim', proposing: false,
      replay: { kind: 'journal', date: '2026-09-24', symbol: null, playhead: at, at, loading: false, error: null,
        note: null, loaded: null, gap: null, journal: null },
      setups: [
        summary('first_pullback', { level: 1, counts: counts(), recorded: true }),
        summary('bull_flag', { recorded: false }),
        summary('flat_top_breakout', { recorded: true }),
        summary('red_to_green', { recorded: true }),
      ],
      rows: board().rows.filter(r => r.setup_type !== 'bull_flag'),
    });
    mockFetch();
    await renderPage();
    expect(screen.getByTestId('bots-sim-line').textContent).toBe('Recorded · what Nova\'s eyes saw live at 08:07:02 ET on 2026-09-24');
    expect(within(screen.getByTestId('bots-setup-bull_flag')).getByTestId('bots-setup-status').textContent)
      .toMatch(/Not running at this moment/);
    expect(screen.getByTestId('bots-scan-empty-flat_top_breakout').textContent).toBe('Nothing forming at 08:07:02 ET.');
  });

  it('a setup\'s own level PATCHes its own level -- Strategy included -- and never {setup}', async () => {
    const fetchMock = mockFetch({ onPatch: body => session({ setup_levels: { ...(body.setup_levels as object) } }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-setup-level-bull_flag-2')); await flush(); });
    await act(async () => { fireEvent.click(screen.getByTestId('bots-setup-level-red_to_green-1')); await flush(); });
    expect(patches(fetchMock)).toEqual([{ setup_levels: { bull_flag: 2 } }, { setup_levels: { red_to_green: 1 } }]);
    expect(patches(fetchMock).some(p => 'setup' in p)).toBe(false);
    fireEvent.click(screen.getByTestId('bots-setup-board-red_to_green'));
    expect(getSetupsFilter()).toBe('red_to_green');
    expect(consumeSetupsBoardOpen()).toBe(true);
  });

  it('an API older than the scanners says the backend needs a reload, never that the scanner is missing', async () => {
    const old = session({ setups: [
      { id: 'first_pullback', scanner: true }, { id: 'gap_and_go', scanner: false },
      { id: 'flat_top_breakout', scanner: false }, { id: 'red_to_green', scanner: false },
      { id: 'micro_pullback', scanner: false },
    ] });
    delete old.setup_levels;
    delete old.breakers;
    const templates = templatesPayload();
    templates.setups = templates.setups.filter(s => s.id !== 'bull_flag');
    mockFetch({ session: old, templates });
    setups.board = board({ schema_version: 1, setups: undefined });
    await renderPage();
    expect(screen.getByTestId('bots-stale-backend').textContent).toMatch(/still running code from before the setup scanners/);
    for (const id of ['bull_flag', 'flat_top_breakout', 'red_to_green']) {
      const card = within(screen.getByTestId(`bots-setup-${id}`));
      expect(card.getByTestId('bots-setup-status').textContent).toMatch(/the backend needs a reload to start this scanner/);
      expect(card.queryByText(/No scanner yet/)).toBeNull();
      const level = screen.getByTestId(`bots-setup-level-${id}-1`) as HTMLButtonElement;
      expect(level.disabled).toBe(true);
      expect(level.getAttribute('data-why')).toMatch(/reload it/);
    }
    expect((screen.getByTestId('bots-setup-template-bull_flag') as HTMLSelectElement).textContent)
      .toBe('needs a backend reload');
    expect(screen.getByTestId('bots-noscan-line').textContent).toMatch(/Gap and Go/);
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

describe('Tickers today -- the hot list and the squares by ticker (ADR 044)', () => {
  it('lists the hot list first with its Buy / Sell, each gate a square, and what stops each ticker', async () => {
    mockFetch();
    await renderPage();
    const table = screen.getByTestId('bots-tickers');
    expect(table.querySelector('h3')?.textContent).toBe('Tickers today 1 on the hot list · 1 more triggered');
    const grml = screen.getByTestId('bots-tk-GRML');
    expect(within(grml).getByText('★')).toBeTruthy();
    expect(within(grml).getByText(/^auto /)).toBeTruthy();
    expect(within(grml).getByText('You trade it')).toBeTruthy();
    // Ten squares in Nova's order: one red, said once in grey as the gate every ticker shares.
    expect(grml.querySelectorAll('.bots-tk__cell')).toHaveLength(10);
    const red = grml.querySelectorAll('.bots-tk__cell.is-bad');
    expect(red).toHaveLength(1);
    expect(red[0].getAttribute('data-tip')).toBe('the bot window 07:00–10:00 closed');
    // What stops it, in a few words; the whole sentence is the hover. A gate every ticker shares is grey.
    const stop = grml.querySelector('.bots-tk__stop') as HTMLElement;
    expect(stop.textContent).toBe('No · outside its bot window');
    expect(stop.querySelector('.bots-muted [data-tip]')?.getAttribute('data-tip')).toBe('the bot window 07:00–10:00 closed');
    // Its trigger today sits under it, judged by the same squares: BLIND is the Level 2 line.
    const past = grml.nextElementSibling as HTMLElement;
    expect(past.className).toBe('bots-tk__past');
    expect(past.textContent).toMatch(/First pullback.*A.*BLIND.*target \+1\.60R/);
    expect(past.querySelector('.bots-tk__stop')?.textContent).toBe('BLIND: no Level 2 line');
    expect(past.querySelector('.bots-tk__stopword')?.getAttribute('data-tip')).toBe('no Level 2 line: the tape was BLIND');
    // Every column head says what its square asks.
    const head = Array.from(table.querySelectorAll('th.bots-tk__gh')).map(th => th.textContent);
    expect(head).toEqual(['Bot on', 'Strategy on', 'Grade', 'Setups a day', 'Bot window', 'Hot list', 'Nova buys',
      'Level 2 line', 'Tape GO', 'Trades today']);
    expect(table.querySelector('th.bots-tk__gh')?.getAttribute('data-tip')).toBe('Was the Bot switch on for this venue?');
    // The tickers that triggered off the list fold into one row until opened, and each one's triggers again.
    expect(screen.queryByTestId('bots-tk-IMCC')).toBeNull();
    expect(screen.getByTestId('bots-tk-unlisted-toggle').textContent).toMatch(/Triggered today, not on your hot list · 1 tickers · 1 triggers/);
    await act(async () => { fireEvent.click(screen.getByTestId('bots-tk-unlisted-toggle')); await flush(); });
    const imcc = screen.getByTestId('bots-tk-IMCC');
    expect(imcc.className).toBe('bots-tk__unlisted');
    expect(imcc.nextElementSibling).toBeNull();
    await act(async () => { fireEvent.click(within(imcc).getByText(/▸ 1/)); await flush(); });
    expect((screen.getByTestId('bots-tk-IMCC').nextElementSibling as HTMLElement).textContent).toMatch(/Bull flag.*stop -1\.00R/);
    // What each gate did to the day.
    expect(screen.getByTestId('bots-tk-impact').textContent)
      .toMatch(/Level 2 line blocked 1 · 1 would have hit target, 0 stopped · 1\.6R missed/);
  });

  it('sets Buy and Sell per stock through Who trades, and says a refusal in the backend\'s words', async () => {
    const fetchMock = mockFetch({ onStockModePut: (symbol, body) => (body.sell === 'nova'
      ? refusal(409, 'STOCK_MODE_HELD', `You hold ${symbol} -- sell it or take over the exit first`) : undefined) });
    await renderPage();
    const grml = within(screen.getByTestId('bots-tk-GRML'));
    const buy = grml.getByRole('radiogroup', { name: 'Buy' });
    await act(async () => { fireEvent.click(within(buy).getByText('Nova')); await flush(); });
    expect(calls(fetchMock, '/stock-mode/GRML', 'PUT').map(c => c.body)).toEqual(['{"buy":"nova","sell":"you"}']);
    const sell = grml.getByRole('radiogroup', { name: 'Sell' });
    await act(async () => { fireEvent.click(within(sell).getByText('Nova')); await flush(); });
    expect(screen.getByTestId('bots-tk-GRML').querySelector('.bots-tk__stop')?.textContent)
      .toMatch(/You hold GRML -- sell it or take over the exit first$/);
  });

  it('stars and unstars from the table, adds a typed ticker, and sets the auto top N', async () => {
    const fetchMock = mockFetch();
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByTestId('bots-tk-unlisted-toggle')); await flush(); });
    await act(async () => { fireEvent.click(within(screen.getByTestId('bots-tk-IMCC')).getByText('☆')); await flush(); });
    expect(calls(fetchMock, '/hot-list/star', 'POST').map(c => c.body)).toEqual(['{"symbol":"IMCC"}']);
    await act(async () => { fireEvent.click(within(screen.getByTestId('bots-tk-GRML')).getByText('★')); await flush(); });
    expect(calls(fetchMock, '/hot-list/GRML', 'DELETE')).toHaveLength(1);
    const input = screen.getByLabelText('Star a stock');
    await act(async () => {
      fireEvent.change(input, { target: { value: 'aisp' } });
      fireEvent.keyDown(input, { key: 'Enter' });
      await flush();
    });
    expect(calls(fetchMock, '/hot-list/star', 'POST').map(c => c.body)).toContain('{"symbol":"AISP"}');
    const auto = screen.getByRole('radiogroup', { name: 'Auto top N' });
    expect(within(auto).getByText('5').getAttribute('aria-checked')).toBe('true');
    await act(async () => { fireEvent.click(within(auto).getByText('10')); await flush(); });
    expect(calls(fetchMock, '/hot-list', 'PATCH').map(c => c.body)).toEqual(['{"auto_n":10}']);
  });

  it('says when the scanners do not follow a listed stock, and why', async () => {
    mockFetch({ hotList: hotListView({ entries: [{ symbol: 'GRML', how: 'star', at: 1_790_000_000, board: null, rank: null,
      change_pct: null, followed: false, why_not_followed: 'HOD Momo\'s 20 reserved slots are full' }] }) });
    await renderPage();
    const tag = screen.getByTestId('bots-tk-unfollowed-GRML');
    expect(tag.textContent).toBe('not followed');
    expect(tag.getAttribute('data-tip')).toBe('HOD Momo\'s 20 reserved slots are full');
  });

  it('brings back yesterday\'s list only when there is one', async () => {
    const fetchMock = mockFetch({ hotList: hotListView({ yesterday: ['NXL', 'ACN'] }) });
    await renderPage();
    await act(async () => { fireEvent.click(screen.getByText('Bring back yesterday\'s 2')); await flush(); });
    expect(calls(fetchMock, '/hot-list/bring-back', 'POST')).toHaveLength(1);
  });

  it('says when the triggers table cannot be read, instead of an empty table', async () => {
    mockFetch({ triggers: { schema_version: 99 } });
    await renderPage();
    expect(within(screen.getByTestId('bots-tickers')).getByRole('alert').textContent)
      .toBe('The triggers table answered in a shape this desk does not read.');
    expect(screen.getByTestId('bots-answer-headline').textContent).not.toMatch(/^Yes/);
  });
});

describe('Level 2 lines (ADR 044)', () => {
  it('shows who holds each of IBKR\'s three lines, and switches lending', async () => {
    const fetchMock = mockFetch({ lines: linesView({ lending: { on: true, loans: [
      { lender: 'NXL', borrower: 'AISP', setup_type: 'first_pullback', setup_id: 'a1', since: null, why: 'near its trigger',
        tier: 'near', text: null, tape: true, tape_state: 'receiving', tape_error: null, tape_lent: true },
      { lender: 'ACN', borrower: 'MEDS', setup_type: 'bull_flag', setup_id: 'm1', since: null, why: 'armed',
        tier: 'armed', text: null, tape: false, tape_state: 'refused', tape_error: 'IBKR 10190: tick-by-tick limit', tape_lent: false },
    ], recent: [] } }) });
    await renderPage();
    expect(screen.getByTestId('bots-line-GRML').textContent).toBe('GRMLyour Trader tab · in front');
    expect(screen.getByTestId('bots-line-NXL').textContent).toBe('NXLyour Trader tab · hidden');
    expect(screen.getByTestId('bots-line-free-2').textContent).toBe('freeno line held');
    expect(screen.getByTestId('bots-lines-loan-NXL').textContent)
      .toBe('Now: NXL\'s lines are lent to AISP (first pullback) · its prints arrive');
    // A borrower without its prints is said, with IBKR's words: no silent BLIND.
    const refused = screen.getByTestId('bots-lines-loan-ACN');
    expect(refused.textContent).toMatch(/no Time & Sales line \(IBKR 10190: tick-by-tick limit\)$/);
    expect(refused.className).toBe('is-bad');
    const lending = screen.getByTestId('bots-lines-lending');
    expect(lending.getAttribute('aria-checked')).toBe('true');
    await act(async () => { fireEvent.click(lending); await flush(); });
    expect(calls(fetchMock, '/ibkr/depth/lending', 'PATCH').map(c => c.body)).toEqual(['{"on":false}']);
    expect(screen.getByTestId('bots-lines-lending').getAttribute('aria-checked')).toBe('false');
  });

  it('says a backend that cannot say who holds the lines needs a reload', async () => {
    mockFetch({ lines: { schema_version: 2 } });
    await renderPage();
    expect((screen.getByTestId('bots-lines-lending') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('Risk sleeve (ADR 042 E: one per venue)', () => {
  it('PATCHes a slider once it is let go, on the venue shown, and names what each binds', async () => {
    const fetchMock = mockFetch({ onPatch: () => session() });
    await renderPage();
    const shares = screen.getByTestId('bot-strategy-max-shares');
    await act(async () => {
      fireEvent.change(shares, { target: { value: '3' } });
      fireEvent.change(shares, { target: { value: '4' } });
      fireEvent.pointerUp(shares);
      await flush();
    });
    expect(patches(fetchMock)).toEqual([{ caps: { venue: 'paper', max_shares: 4 } }]);
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-risk'), { target: { value: '35' } });
      fireEvent.blur(screen.getByTestId('bot-strategy-risk'));
      fireEvent.change(screen.getByTestId('bot-strategy-entries'), { target: { value: '2' } });
      fireEvent.blur(screen.getByTestId('bot-strategy-entries'));
      fireEvent.click(screen.getByTestId('bot-strategy-eh'));
      await flush();
    });
    expect(patches(fetchMock)).toEqual(expect.arrayContaining([
      { caps: { venue: 'paper', risk_usd: 35 } },
      { caps: { venue: 'paper', entries_per_day: 2 } },
      { caps: { venue: 'paper', extended_hours: true } },
    ]));
    const risk = screen.getByTestId('bots-risk');
    expect(within(risk).getByText('Risk per trade').getAttribute('data-tip'))
      .toBe('Sizes every Nova buy and your Stage: shares = risk ÷ risk per share, capped by max shares and the budget.');
    expect(within(risk).getByText('Nova entries a day').getAttribute('data-tip')).toMatch(/One count for the bot and Auto-entry/);
    expect(screen.getByTestId('bots-sleeve-kinds').textContent).toMatch(/Order kinds \(the localhost bot API\)/);
  });

  it('switches to another venue\'s sleeve and saves it there', async () => {
    const fetchMock = mockFetch({ session: session({ caps_by_venue: {
      paper: caps('paper'), sim: caps('sim', { max_shares: 5 }), live: caps('live'),
    } }), onPatch: () => undefined });
    await renderPage();
    fireEvent.click(screen.getByTestId('bots-sleeve-tab-sim'));
    expect((screen.getByTestId('bot-strategy-max-shares') as HTMLInputElement).value).toBe('5');
    await act(async () => {
      fireEvent.change(screen.getByTestId('bot-strategy-max-shares'), { target: { value: '6' } });
      fireEvent.pointerUp(screen.getByTestId('bot-strategy-max-shares'));
      await flush();
    });
    expect(patches(fetchMock)).toEqual([{ caps: { venue: 'sim', max_shares: 6 } }]);
    fireEvent.click(screen.getByTestId('bots-sleeve-tab-live'));
    expect(screen.getByTestId('bots-risk').textContent).toMatch(/Nova buys nothing by itself on Live/);
  });

  it('draws the desk venue\'s breakers and today\'s P&L on one bar (ADR 032)', async () => {
    mockFetch({ dayPnl: -9.54 });
    await renderPage();
    const bar = screen.getByTestId('bot-strategy-breakers').textContent ?? '';
    expect(bar).toMatch(/Paper · drag to move · defaults/);
    expect(screen.getByTestId('bots-breaker-hard-label').textContent).toBe('−$200 all-stop');
    expect(screen.getByTestId('bots-breaker-soft-label').textContent).toBe('−$50 bot trip');
    expect(screen.getByTestId('bots-breaker-today').textContent).toBe('−$9.54 today');
    expect(parseFloat((screen.getByTestId('bots-breaker-now') as HTMLElement).style.left)).toBeCloseTo(96.184, 3);
    expect(parseFloat((screen.getByTestId('bots-breaker-soft') as HTMLElement).style.left)).toBeCloseTo(80, 6);
    expect(screen.getByTestId('bots-breaker-soft').getAttribute('data-tip')).toMatch(/^Bot trip: when this venue's day P&L/);
    expect(screen.queryByTestId('bots-breaker-status')).toBeNull();
  });

  it('says when the bot trip fired, at what P&L, when it clears -- and that a replay compares nothing', async () => {
    mockFetch({ session: session({
      soft_breaker: { fired: true, at: AT_0942, pnl: -52.1, until: '2026-10-01T04:00:00-04:00' },
      breakers: breakers({ note: 'A Sim replay is not today -- the breakers compare nothing here' }),
    }) });
    await renderPage();
    expect(screen.getByTestId('bots-breaker-soft-fired').textContent).toBe('Bot trip fired at 09:42 ET at −$52.10: the bot '
      + 'is off on this venue until 04:00 ET on Oct 1; turning it back on asks you first.');
    expect(screen.getByTestId('bots-breaker-note').textContent).toBe('A Sim replay is not today — the breakers compare nothing here');
  });

  it('drags the bot trip and saves the venue\'s pair on release', async () => {
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
    expect(JSON.stringify(confirmApp.mock.calls[0])).toMatch(/Loosen Live/);
    expect(patches(fetchMock)).toEqual([]);
    expect(screen.getByTestId('bots-breaker-soft-label').textContent).toBe('−$50 bot trip');
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

  it('says the bot is taking a proposal, and locks Stage so it is not bought twice', async () => {
    setups.board = board({ proposals: [{ ...board().proposals[0], taken_by: 'bot', not_a_trade: null } as never] });
    mockFetch();
    await renderPage();
    expect(screen.getByTestId('bots-proposal-taken-GRML').textContent).toBe('The bot is taking this — nothing to do');
    const stage = screen.getByTestId('bots-stage-GRML') as HTMLButtonElement;
    expect(stage.disabled).toBe(true);
    expect(stage.getAttribute('data-why')).toMatch(/Nova's bot is taking this trigger/);
  });

  it('says why a proposal is not a trade, and locks Stage with the reasons', async () => {
    setups.board = board({ proposals: [{ ...board().proposals[0], taken_by: null,
      not_a_trade: { reasons: ['grade C (1 of 5 pillars)', 'the spread is at least the risk'] } } as never] });
    mockFetch();
    await renderPage();
    expect(screen.getByTestId('bots-proposal-not-a-trade-GRML').textContent)
      .toBe('Not a trade: grade C (1 of 5 pillars); the spread is at least the risk');
    const stage = screen.getByTestId('bots-stage-GRML') as HTMLButtonElement;
    expect(stage.disabled).toBe(true);
    expect(stage.getAttribute('data-why')).toMatch(/^Not a trade -- grade C/);
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

  it('draws the day\'s timeline: the master level, why the bot stopped, who trades, the scanner', async () => {
    mockFetch({
      audit: [
        { timestamp: 1_790_000_300, level: 1, strategy: null, brain_session_id: null, action: 'level',
          inputs: { from: 1, to: 2 }, reason: null, order_id: null, advise_spend: null, outcome: '1->2' },
        { timestamp: 1_790_000_350, level: 2, brain_session_id: null, action: 'deactivate',
          inputs: { reason: 'restart' }, reason: null, order_id: null, outcome: 'ok' },
        { timestamp: 1_790_000_360, level: 2, brain_session_id: null, action: 'stock_mode',
          inputs: { symbol: 'GRML', setup_type: 'bull_flag' }, reason: 'outside the bull flag\'s bot window 07:00-10:00',
          order_id: null, outcome: 'skipped' },
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
    expect(activity.getByText('Master level Eyes → Strategy')).toBeTruthy();
    expect(activity.getByText('Stopped the bot')).toBeTruthy();
    expect(activity.getByText('the backend restarted')).toBeTruthy();
    expect(activity.getByText('Skipped GRML · bull flag')).toBeTruthy();
    expect(activity.getByText('outside the bull flag\'s bot window 07:00-10:00')).toBeTruthy();
    expect(activity.getByText('Proposed GRML first pullback')).toBeTruthy();
    expect(activity.getByText('Armed GRML · First pullback · trigger 8.72 · stop 8.52')).toBeTruthy();
    expect(activity.getByText('Wait IMCC near 1.45')).toBeTruthy();
    await act(async () => { fireEvent.click(activity.getByText('Proposals')); });
    expect(activity.queryByText('Master level Eyes → Strategy')).toBeNull();
    expect(activity.getByText('Proposed GRML first pullback')).toBeTruthy();
  });

  it('says what each of today\'s counts counts, and reads the setup at Strategy first', async () => {
    mockFetch({ session: strategySession({ entries_today: { count: 1, cap: 1, venue_day: '2026-09-30', entries: [], approved: 2 } }) });
    await renderPage();
    const today = screen.getByTestId('bots-today');
    expect(today.textContent).not.toMatch(/bot only/);
    expect((screen.getByTestId('bots-today-setup') as HTMLSelectElement).value).toBe('first_pullback');
    expect(screen.getByTestId('bots-kpi-armed').textContent).toBe('6');
    expect(screen.getByTestId('bots-kpi-triggered').textContent).toBe('2');
    expect(screen.getByTestId('bots-kpi-entries').textContent).toBe('1 / 1');
    expect(screen.getByTestId('bots-kpi-armed').parentElement?.textContent).toBe('Armed6First pullback');
    expect(screen.getByTestId('bots-kpi-proposed').parentElement?.textContent).toBe('Proposed0every setup');
    expect(screen.getByTestId('bots-kpi-pnl').parentElement?.textContent).toBe('Bot P&L—its own fills');
    const table = within(screen.getByTestId('bots-scoreboard'));
    expect(table.getByText('GO')).toBeTruthy();
    expect(table.getByText('+0.31R')).toBeTruthy();
    // Paper with no ledger answer yet: the bot's P&L is unknown, never $0.
    expect(screen.getByTestId('bots-kpi-pnl').textContent).toBe('—');
    expect(screen.getByTestId('bots-kpi-entries-note').textContent).toBe('bot + Auto-entry · 2 approved by you');
  });

  it('states the bot footer: working orders and the order kinds of the localhost bot API', async () => {
    mockFetch({ session: session({ caps: caps('paper', { api_kinds: ['buy_market', 'exit_pos'], allowlist: ['buy_market', 'exit_pos'] }) }) });
    await renderPage();
    const footer = screen.getByTestId('bots-status').textContent ?? '';
    expect(footer).toMatch(/GRML · flat · 0 bot working orders/);
    expect(footer).toMatch(/Order kinds \(the localhost bot API\): buy_market · exit_pos/);
  });
});
