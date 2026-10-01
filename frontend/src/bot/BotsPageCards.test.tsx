/**
 * @vitest-environment jsdom
 *
 * The Bots page cards (approved mockup v4, ADR 042): every control is a real one -- each
 * setup's own level under the master, the add-a-setup door, who trades each stock, the
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
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsPage } from './BotsPage';
import {
  botsFetchRouter, breakers, caps, refusal, session, setupRow, strategySession, templatesPayload, type BotsFetchOpts,
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
});

afterEach(() => {
  cleanup();
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

describe('Strategies card (ADR 042: a level per setup under the master)', () => {
  it('gives every setup with a scanner its own Off / Eyes / Strategy, and no chosen setup', async () => {
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
    // The card shows its own level, and what it may do under the master.
    expect(screen.getByTestId('bots-setup-level-first_pullback-2').getAttribute('aria-checked')).toBe('true');
    expect(within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Strategy · capped to Eyes by the bot\'s level');
    expect(within(screen.getByTestId('bots-setup-bull_flag')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Eyes · pings on near + go');
    expect(within(screen.getByTestId('bots-setup-flat_top_breakout')).getByTestId('bots-setup-level-chip').textContent)
      .toBe('Off · scores silently');
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

  it('a setup without a scanner says only why it can\'t watch yet and what unblocks it', async () => {
    mockFetch();
    await renderPage();
    for (const id of ['gap_and_go', 'micro_pullback']) {
      expect(screen.getByTestId(`bots-noscan-${id}`).textContent).toMatch(/Why it can't watch yet\..*Unblocks when/);
      expect(screen.queryByTestId(`bots-setup-template-${id}`)).toBeNull();
      expect(screen.queryByTestId(`bots-setup-params-${id}`)).toBeNull();
      expect(screen.queryByTestId(`bots-setup-level-${id}-0`)).toBeNull();
    }
    expect(screen.getByTestId('bots-noscan-micro_pullback').textContent).toMatch(/one-second bars/);
    expect(within(screen.getByTestId('bots-setup-gap_and_go')).getByText('Bars alone: failed')).toBeTruthy();
    expect(screen.queryByText(/Halt \/ LULD|Quote spike|Volume boost|LLM decide/)).toBeNull();
  });

  it('a setup at Strategy proposes like Eyes until the bot is active, and says so', async () => {
    mockFetch({ session: strategySession() });
    await renderPage();
    const chip = within(screen.getByTestId('bots-setup-first_pullback')).getByTestId('bots-setup-level-chip');
    expect(chip.textContent).toBe('Strategy · proposes until Activate');
    expect(chip.getAttribute('data-tip')).toMatch(/the bot is not active on this venue, so it proposes like Eyes/);
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
    expect(screen.getByTestId('bots-noscan-gap_and_go').textContent).toMatch(/Why it can't watch yet/);
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

describe('Who trades -- the stocks Nova may buy (ADR 042 F)', () => {
  const view = (symbol: string, mode: string, partial: Record<string, unknown> = {}) => ({
    symbol, generated_at: 0, venue: 'paper', mode, buy: mode === 'approve' ? 'you' : 'nova', sell: mode === 'bot' ? 'nova' : 'you',
    risk_usd: 20, set_at: 0, locks: { buy: null, sell: null }, notes: [], approval: null, trade: null,
    entries_today: { count: 0, cap: 1 }, last_event: null, bot: null, size: null, ...partial,
  });

  it('lists every stock Nova may buy with its mode, its Level 2 line, its setups and what keeps Nova from acting', async () => {
    mockFetch({ stockModes: [
      view('GRML', 'bot', { notes: [{ id: 'not_active', tone: 'warn', text: 'The bot is not active -- press Activate' },
        { id: 'window', tone: 'info', text: 'Every bot window is closed' }] }),
      view('IMCC', 'bot'),
      view('QNME', 'auto_entry'),
      view('SIGN', 'signal'),
    ] });
    await renderPage();
    expect(screen.getByTestId('bots-symbols').querySelector('h3')?.textContent).toBe('Who trades');
    expect(screen.getByTestId('bots-symbols-note').textContent)
      .toBe('Stocks Nova\'s bot may trade — set per stock under Who trades. The scanners and Eyes watch every HOD Momo name, whatever this list says.');
    expect(screen.getByTestId('bots-entries-today').textContent).toBe('Nova\'s buys today: 0 of 1');
    expect(screen.getByTestId('bots-symbol-mode-GRML').textContent).toBe('Bot');
    expect(screen.getByTestId('bots-symbol-mode-QNME').textContent).toBe('Auto-entry');
    expect(screen.queryByTestId('bots-symbol-SIGN')).toBeNull();
    const notes = screen.getByTestId('bots-symbol-notes-GRML');
    expect(notes.textContent).toBe('The bot is not active — press Activate · +1');
    expect(notes.getAttribute('data-tip')).toMatch(/Every bot window is closed/);
    expect(within(screen.getByTestId('bots-symbol-GRML')).getByText('Held · Trader')).toBeTruthy();
    fireEvent.click(screen.getByTestId('bots-symbol-open-l2-IMCC'));
    expect(openStockView).toHaveBeenCalledWith('IMCC', { pin: true });
    expect(screen.getByTestId('bots-symbol-setup-GRML-first_pullback').textContent).toBe('First pullback · Near');
    // A stock at Auto-entry is changed on its own Who trades row: the card opens it.
    expect(screen.queryByTestId('bots-symbol-remove-QNME')).toBeNull();
    fireEvent.click(screen.getByTestId('bots-symbol-open-QNME'));
    expect(openStockView).toHaveBeenCalledWith('QNME', { pin: true });
  });

  it('adds and removes through POST /bot/allowlist, and shows a refusal in the backend\'s words', async () => {
    const ops: Array<{ symbol: string; op: string }> = [];
    let list = ['GRML', 'IMCC'];
    mockFetch({ onAllowlist: body => {
      ops.push(body);
      if (body.symbol === 'HELD') return refusal(409, 'STOCK_MODE_HELD', 'You hold HELD -- sell it or take over the exit first');
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
    await act(async () => {
      fireEvent.change(screen.getByTestId('bots-symbol-input'), { target: { value: 'held' } });
      fireEvent.click(screen.getByTestId('bots-symbol-add'));
      await flush();
    });
    expect(screen.getByTestId('bots-symbol-refusal').textContent).toBe('You hold HELD — sell it or take over the exit first');
    expect((screen.getByTestId('bots-symbol-input') as HTMLInputElement).value).toBe('HELD');
    await act(async () => { fireEvent.click(screen.getByTestId('bots-symbol-remove-IMCC')); await flush(); });
    expect(ops).toContainEqual({ symbol: 'IMCC', op: 'remove' });
  });

  it('says when Who trades cannot be read, instead of an empty list', async () => {
    mockFetch({ stockModes: refusal(503, 'STOCK_MODE_DOWN', 'The stock-mode store is not open') });
    await renderPage();
    expect(screen.getByTestId('bots-stock-modes-error').textContent).toMatch(/Who trades did not load — The stock-mode store is not open/);
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
      + 'is off on this venue until 04:00 ET on Oct 1 — Activate re-enables it for today.');
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
    expect(screen.getByTestId('bots-entries-today').textContent).toBe('Nova\'s buys today: 1 of 1 · 2 approved by you');
  });

  it('states the bot footer: working orders and the order kinds of the localhost bot API', async () => {
    mockFetch({ session: session({ caps: caps('paper', { api_kinds: ['buy_market', 'exit_pos'], allowlist: ['buy_market', 'exit_pos'] }) }) });
    await renderPage();
    const footer = screen.getByTestId('bots-status').textContent ?? '';
    expect(footer).toMatch(/GRML · flat · 0 bot working orders/);
    expect(footer).toMatch(/Order kinds \(the localhost bot API\): buy_market · exit_pos/);
  });
});
