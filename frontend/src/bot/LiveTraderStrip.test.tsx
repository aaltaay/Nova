/**
 * @vitest-environment jsdom
 *
 * The Live Trader bots on Bots > LiveTrader Bots (ADR 055; each host's bot in the host's card since 2026-10-15, approved
 * from a render): every control is a real one -- a host's key (off places no order and sells nothing, so it asks
 * nothing), Entry and Exit, Rules and their editor, an ask's Approve and Skip on the card and as a toast in every
 * window -- every skip and blocker is said, and a copy the bot holds is a chip on the row it copies. Made-up hosts and
 * tickers.
 */
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FollowedTrade } from '../followed_traders';
import { BotNotices } from './BotNotices';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { LiveTraderBadge } from './LiveTraderBadge';
import { firstClause, skipsTip } from './liveTraderFormat';
import { LiveTraderHead } from './LiveTraderHead';
import { _resetLiveTraderPollsForTests } from './liveTraderStore';
import { LiveTraderStrip } from './LiveTraderStrip';
import type { LiveTradersView, LtAsk, LtEvent, LtHost } from './liveTraderTypes';

const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));
vi.mock('../followed_traders', () => ({ useFollowedTradersEnabled: () => true }));
const setSwitch = vi.fn(async () => null);
const botSession: { level_venue: string } = { level_venue: 'paper' };
vi.mock('./useBotSession', () => ({
  useBotSession: () => ({ session: botSession, proposals: [], audit: [], error: null, busy: false, setSwitch,
    patch: vi.fn(), setKey: vi.fn() }),
}));
vi.mock('./botSwitch', () => ({ botOn: () => true, switchLock: () => null }));

const NOW = Date.now() / 1000;
const BOT_OFF = 'the Bot switch in the header is off: bots place no order, not even a sell';

function host(over: Partial<LtHost> = {}): LtHost {
  return {
    name: 'ALPHA', face: null, on_air: true, left_ts: null,
    settings: { key: true, entry: 'nova', exit: 'nova', step_usd: 500, adds: 2, allowance_usd: 2500, sides: 'both',
      short_stop_pct: 5, take_open: true, mode: 'bot' },
    state: { tone: 'ok', text: 'On air · read 2 s ago' },
    allowance: { used_usd: 954, of_usd: 2500 },
    today: { pl_usd: 6.85, realized_usd: 3.52, unrealized_usd: 3.33, trades: 3, skipped: 2,
      series: [[NOW - 600, 1.2], [NOW - 300, 3.52], [NOW, 6.85]] },
    positions: [{ id: 'ALPHA|long|XYZ', row_id: 'ALPHA|long|XYZ|1', symbol: 'XYZ', side: 'long', qty: 4, avg_cost: 100.02,
      their_avg: 100.0, now: 100.44, pl_usd: 1.68, steps: 1, adds_followed: 0, opened_ts: NOW - 300, state: 'open',
      order_id: null, note: null }],
    asks: [],
    events: [
      { ts: NOW - 90, tone: 'ok', outcome: 'order', symbol: 'XYZ', code: null, late_sec: 4,
        text: 'buy 4 XYZ at 100.04 -- ALPHA bought it at 100.00' },
      { ts: NOW - 60, tone: 'warn', outcome: 'skipped', symbol: 'QQQQ', code: 'LT_SMALL_CAP', late_sec: 3,
        text: 'a small cap ($2.1B): this bot copies large caps only ($10.0B and up)' },
      { ts: NOW - 30, tone: 'warn', outcome: 'skipped', symbol: 'RRRR', code: 'LT_SMALL_CAP', late_sec: 3,
        text: 'a small cap ($2.1B): this bot copies large caps only ($10.0B and up)' },
    ],
    ...over,
  };
}

function view(over: Partial<LiveTradersView> = {}): LiveTradersView {
  return {
    schema_version: 1, generated_at: NOW, enabled: true, venue: 'paper', desk_venue: 'paper',
    can_trade: { ok: true, code: null, why: null }, sell_all_at: '15:55', sell_all_ts: null,
    watcher: { running: true, pass_ts: NOW, idle: false, text: 'Watching the bar, read 2 s ago',
      feed: { state: 'ok', error: null, read_age_sec: 2, behind_sec: 3, bar_visible: true, live: true } },
    settings_error: null, book_error: null, hosts: [host()], defaults: {}, bounds: {}, ...over,
  };
}

function ask(over: Partial<LtAsk> = {}): LtAsk {
  return { id: 'bravo-3', host: 'BRAVO', row_id: 'BRAVO|short|FADE|9', symbol: 'FADE', side: 'short', step: 'entry',
    their_price: 40, qty: 12, limit: 39.97, stop: 41.97, created_ts: NOW - 5, expires_ts: NOW + 55,
    text: 'BRAVO shorted FADE at 40.00: short 12 at 39.97, buy stop 41.97?', approved: false, answered: null,
    seconds_left: 55, ...over };
}

/** A host's open trade on the followed traders' page, as much of it as the bot reads. */
function openTrade(id: string, symbol: string): FollowedTrade {
  return { id, trader: 'ALPHA', side: 'long', symbol, status: 'open' } as unknown as FollowedTrade;
}

let current: LiveTradersView;
let asksNow: { asks: LtAsk[]; held: { host: string; symbol: string; side: string; qty: number; state: string }[] };
const writes: { url: string; method: string; body: unknown }[] = [];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  _resetLiveTraderPollsForTests();
  current = view();
  asksNow = { asks: [], held: [] };
  writes.length = 0;
  confirmApp.mockClear();
  confirmApp.mockImplementation(async () => true);
  setSwitch.mockClear();
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    if (method !== 'GET') {
      const body = init?.body ? JSON.parse(String(init.body)) : null;
      writes.push({ url, method, body });
      if (url.includes('/asks/')) return json(current);
      const name = url.split('/').pop() as string;
      current = view({ hosts: current.hosts.map(h => (h.name === name ? { ...h, settings: { ...h.settings, ...body } } : h)) });
      return json(current);
    }
    if (url.includes('/api/bot/live-traders/asks')) return json({ schema_version: 1, generated_at: NOW, ...asksNow });
    if (url.includes('/api/bot/live-traders')) return json(current);
    return json({});
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  _resetLiveTraderPollsForTests();
});

async function flush() {
  for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); });
}

async function renderStrip(open: FollowedTrade[] = [openTrade('ALPHA|long|XYZ|1', 'XYZ')], name = 'ALPHA') {
  render(<LiveTraderStrip name={name} open={open} />);
  await flush();
}

const tip = (id: string) => screen.getByTestId(id).getAttribute('data-tip');

describe("a host's bot in the host's card", () => {
  it('reads in two lines: its key, Entry, Exit and Rules; its allowance, today and skips', async () => {
    await renderStrip();
    expect(screen.getByTestId('lt-key-ALPHA').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('lt-entry-ALPHA-nova').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('lt-exit-ALPHA-nova').getAttribute('aria-checked')).toBe('true');
    // Who enters and exits, in the stock's own words, is the switches' hover.
    expect(screen.getByTestId('lt-entry-ALPHA').parentElement!.getAttribute('data-tip')).toBe('bot enters · bot exits');
    expect(tip('lt-rules-ALPHA')).toContain('Longs and shorts · 5% buy stop');
    expect(tip('lt-rules-ALPHA')).toContain('Sells all at 15:55');
    expect(screen.getByTestId('lt-allowance-ALPHA').textContent).toBe('$954 of $2,500');
    expect(screen.getByTestId('lt-pl-ALPHA').textContent).toBe('+$6.85');
    expect(screen.getByTestId('lt-trades-ALPHA').textContent).toBe('· 3 trades ·');
    expect(tip('lt-trades-ALPHA')).toContain('buy 4 XYZ at 100.04 — ALPHA bought it at 100.00');
    expect(screen.getByTestId('lt-skips-ALPHA').textContent).toBe('2 skipped');
    // The skips by reason, each reason once with its stocks under it -- not the panel's repeated lines.
    const skips = tip('lt-skips-ALPHA')!;
    expect(skips.match(/large caps only/g)).toHaveLength(1);
    expect(skips).toMatch(/QQQQ \d\d:\d\d · RRRR \d\d:\d\d/);
  });

  it('says nothing while it reads nothing for the host, and a host it does not copy has no bot', async () => {
    await renderStrip([], 'NOBODY');
    expect(screen.queryByTestId('lt-strip-NOBODY')).toBeNull();
  });

  it('turns its key off in one press while it holds a copy: it sells nothing, so it asks nothing', async () => {
    await renderStrip();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-key-ALPHA')); });
    await flush();
    expect(confirmApp).not.toHaveBeenCalled();
    expect(writes).toEqual([{ url: expect.stringContaining('/api/bot/live-traders/ALPHA'), method: 'PATCH', body: { key: false } }]);
    expect(screen.getByTestId('lt-key-ALPHA').getAttribute('aria-checked')).toBe('false');
  });

  it('turns its key on with no question, and changes who enters', async () => {
    current = view({ hosts: [host({ settings: { ...host().settings, key: false }, positions: [] })] });
    await renderStrip([]);
    await act(async () => { fireEvent.click(screen.getByTestId('lt-key-ALPHA')); });
    await flush();
    expect(confirmApp).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-entry-ALPHA-you')); });
    await flush();
    expect(writes.map(w => w.body)).toEqual([{ key: true }, { entry: 'you' }]);
  });

  it('puts an ask waiting on you in its second line, and Approve answers it', async () => {
    current = view({ hosts: [host({ name: 'BRAVO', asks: [ask()] })] });
    await renderStrip([], 'BRAVO');
    expect(screen.getByTestId('lt-ask-bravo-3').textContent).toContain('BRAVO shorted FADE at 40.00');
    expect(screen.getByTestId('lt-ask-bravo-3').textContent).toContain('55 s left');
    expect(screen.queryByTestId('lt-allowance-BRAVO')).toBeNull();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-ask-approve-bravo-3')); });
    await flush();
    expect(writes).toEqual([{ url: expect.stringContaining('/api/bot/live-traders/BRAVO/asks/bravo-3'), method: 'POST',
      body: { approve: true } }]);
  });

  it('opens its rules in a card under Rules, changes them there, and closes on Done', async () => {
    await renderStrip();
    fireEvent.click(screen.getByTestId('lt-rules-ALPHA'));
    const card = screen.getByTestId('lt-rules-card-ALPHA');
    expect(card.parentElement).toBe(document.body);        // over the page: the host's card clips what overflows it
    expect(card.textContent).toContain('Paper only, never Live');
    expect(card.textContent).toContain('Takes already open');
    await act(async () => { fireEvent.click(screen.getByTestId('lt-edit-adds-ALPHA-4')); });
    await flush();
    const step = screen.getByTestId('lt-edit-step_usd-ALPHA');
    fireEvent.change(step, { target: { value: '250' } });
    await act(async () => { fireEvent.blur(step); });
    await flush();
    expect(writes.map(w => w.body)).toEqual([{ adds: 4 }, { step_usd: 250 }]);
    fireEvent.click(screen.getByTestId('lt-rules-done-ALPHA'));
    expect(screen.queryByTestId('lt-rules-card-ALPHA')).toBeNull();
  });

  it('says a write the backend refused, in its second line', async () => {
    await renderStrip();
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: { reason: 'LIVE_TRADER_INVALID', error: 'step_usd is a number from 50 to 10000' } }, 400)));
    fireEvent.click(screen.getByTestId('lt-rules-ALPHA'));
    const step = screen.getByTestId('lt-edit-step_usd-ALPHA');
    fireEvent.change(step, { target: { value: '5' } });
    await act(async () => { fireEvent.blur(step); });
    await flush();
    expect(screen.getByTestId('lt-error-ALPHA').textContent).toContain('step_usd is a number from 50 to 10000');
  });
});

describe('a copy the bot holds', () => {
  it('is a chip on the open row it copies, its shares, entry and P/L on hover', async () => {
    render(<LiveTraderBadge trade={openTrade('ALPHA|long|XYZ|1', 'XYZ')} />);
    await flush();
    const chip = screen.getByTestId('lt-badge-ALPHA|long|XYZ|1');
    expect(chip.textContent).toBe('BOT 4 sh');
    expect(chip.getAttribute('data-tip')).toBe('Holds 4 shares of XYZ long, in at 100.02 · their average 100.00 · now 100.44: +$1.68');
  });

  it('is nothing on a row the bot does not copy', async () => {
    render(<LiveTraderBadge trade={openTrade('ALPHA|long|ABCD|2', 'ABCD')} />);
    await flush();
    expect(screen.queryByTestId('lt-badge-ALPHA|long|ABCD|2')).toBeNull();
  });

  it("is said on the bot's own line when the host's row is not open (a key held its close)", async () => {
    await renderStrip([]);
    expect(screen.getByTestId('lt-held-ALPHA|long|XYZ').textContent).toBe('BOT 4 sh XYZ');
    cleanup();
    _resetLiveTraderPollsForTests();
    await renderStrip();
    expect(screen.queryByTestId('lt-held-ALPHA|long|XYZ')).toBeNull();
  });
});

describe("the head's line", () => {
  async function renderHead() {
    render(<LiveTraderHead />);
    await flush();
  }

  it("says what stops every host's bot once, the reason's first clause on screen and all of it on hover", async () => {
    resetNavRailStoreForTests();
    current = view({ can_trade: { ok: false, code: 'LT_BOT_OFF', why: BOT_OFF } });
    await renderHead();
    const line = screen.getByTestId('lt-blocker');
    expect(line.textContent).toBe('No orders · the Bot switch in the header is off');
    expect(line.getAttribute('data-tip')).toBe(BOT_OFF);
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();          // the switch is in the header, on every page
  });

  it('links Strategy Bots for Freeze all orders, and only for it', async () => {
    resetNavRailStoreForTests();
    current = view({ can_trade: { ok: false, code: 'LT_FROZEN', why: 'Freeze all orders is on: no new orders' } });
    await renderHead();
    fireEvent.click(screen.getByTestId('lt-open-bots'));
    expect(getNavPage()).toBe('bots-strategy');
    cleanup();
    _resetLiveTraderPollsForTests();
    current = view({ can_trade: { ok: false, code: 'LT_VENUE', why: 'the desk is on Live: the Live Trader bot trades Paper only' } });
    await renderHead();
    expect(screen.getByTestId('lt-blocker').textContent).toBe('No orders · the desk is on Live');
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();
  });

  it('says a book it cannot write in red, and nothing when every host may trade', async () => {
    current = view({ book_error: 'the holdings file cannot be written: disk full', can_trade: { ok: false, code: 'LT_BOT_OFF', why: BOT_OFF } });
    await renderHead();
    expect(screen.getByTestId('lt-head-error').textContent).toBe('the holdings file cannot be written');
    expect(screen.queryByTestId('lt-blocker')).toBeNull();
    cleanup();
    _resetLiveTraderPollsForTests();
    current = view();
    await renderHead();
    expect(screen.queryByTestId('lt-blocker')).toBeNull();
    expect(screen.queryByTestId('lt-head-error')).toBeNull();
  });
});

describe('the words', () => {
  it("take a reason's first clause, never cutting at a clock", () => {
    expect(firstClause(BOT_OFF)).toBe('the Bot switch in the header is off');
    expect(firstClause('after the sell-all time 15:55: no new steps')).toBe('after the sell-all time 15:55');
  });

  it('group the newest skips by reason and say how many of the day they are', () => {
    const e = (symbol: string, text: string): LtEvent => ({ ts: NOW, tone: 'warn', outcome: 'skipped', symbol, text, code: null, late_sec: 1 });
    const got = skipsTip([e('AAAA', 'one'), e('BBBB', 'two'), e('CCCC', 'one')], 29)!;
    expect(got.split('\n')).toEqual([
      'one', expect.stringMatching(/^ {3}AAAA \d\d:\d\d · CCCC \d\d:\d\d$/),
      'two', expect.stringMatching(/^ {3}BBBB \d\d:\d\d$/),
      '(the newest 3 of 29)',
    ]);
    expect(skipsTip([], 0)).toBeNull();
  });
});

describe('the asks as toasts', () => {
  it('show in every window with Skip and Approve, and Skip answers the ask', async () => {
    asksNow = { asks: [ask()], held: [] };
    render(<BotNotices />);
    await flush();
    expect(screen.getByTestId('lt-ask-toast-bravo-3').textContent).toContain('BRAVO shorted FADE at 40.00');
    await act(async () => { fireEvent.click(screen.getByTestId('lt-ask-toast-skip-bravo-3')); });
    await flush();
    expect(writes).toEqual([{ url: expect.stringContaining('/api/bot/live-traders/BRAVO/asks/bravo-3'), method: 'POST',
      body: { approve: false } }]);
  });
});

describe('the Bot switch', () => {
  it('turns off in one press while the Live Trader bot holds positions: off sells nothing (2026-10-15)', async () => {
    const { useBotArm } = await import('./useBotArm');
    asksNow = { asks: [], held: [{ host: 'ALPHA', symbol: 'XYZ', side: 'long', qty: 4, state: 'open' }] };
    const { result } = renderHook(() => useBotArm());
    await act(async () => { await result.current.onSwitch(false); });
    expect(confirmApp).not.toHaveBeenCalled();
    expect(setSwitch).toHaveBeenCalledWith(false);
  });

  it('turns off with no question when the bot holds nothing', async () => {
    const { useBotArm } = await import('./useBotArm');
    const { result } = renderHook(() => useBotArm());
    await act(async () => { await result.current.onSwitch(false); });
    expect(confirmApp).not.toHaveBeenCalled();
    expect(setSwitch).toHaveBeenCalledWith(false);
  });
});
