/**
 * @vitest-environment jsdom
 *
 * The Live Trader panel (ADR 055, mockup v1 approved 2026-10-14; on the TraderTV LIVE page since the ADR 044
 * amendment of 2026-10-15): every control is a real one -- a host's key (asks first when it holds positions), Entry
 * and Exit, an ask's Approve and Skip on the card and as a toast in every window, the money rules' editors -- and
 * every blocker is said, with a link to the Bots page when its control is there. Made-up hosts and tickers.
 */
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BotLiveTradersCard } from './BotLiveTradersCard';
import { BotNotices } from './BotNotices';
import { getNavPage, resetNavRailStoreForTests } from '../workspace/navRailStore';
import { _resetLiveTraderPollsForTests } from './liveTraderStore';
import type { LiveTradersView, LtAsk, LtHost } from './liveTraderTypes';

const confirmApp = vi.fn(async () => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (...args: unknown[]) => confirmApp(...(args as [])) }));
vi.mock('../followed_traders', () => ({ useFollowedTradersEnabled: () => true }));
const setSwitch = vi.fn(async () => null);
const botSession: { level_venue: string } = { level_venue: 'paper' };
vi.mock('./useBotSession', () => ({
  useBotSession: () => ({ session: botSession, proposals: [], audit: [], error: null, busy: false, setSwitch,
    patch: vi.fn() }),
}));
vi.mock('./botSwitch', () => ({ botOn: () => true, switchLock: () => null, tripLatch: () => null, reenableWords: () => '' }));

const NOW = Date.now() / 1000;

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
    events: [{ ts: NOW - 60, tone: 'warn', outcome: 'skipped', symbol: 'QQQQ', code: 'LT_SMALL_CAP', late_sec: 3,
      text: 'a small cap ($2.1B): this bot copies large caps only ($10.0B and up)' }],
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

async function renderCard() {
  render(<BotLiveTradersCard />);
  await flush();
}

describe('the Live Trader cards', () => {
  it('draw a host as the mockup does: on air, Entry and Exit, allowance, P/L, positions, the reasons', async () => {
    await renderCard();
    expect(screen.getByTestId('bots-live-traders').textContent).toContain('Live Traders · TraderTV');
    expect(screen.getByTestId('lt-state-ALPHA').textContent).toBe('On air · read 2 s ago');
    expect(screen.getByTestId('lt-mode-ALPHA').textContent).toBe('bot enters · bot exits');
    expect(screen.getByTestId('lt-allowance-ALPHA').textContent).toBe('$954 of $2,500');
    expect(screen.getByTestId('lt-pl-ALPHA').textContent).toBe('+$6.85');
    expect(screen.getByTestId('lt-positions-ALPHA').textContent).toContain('XYZ');
    expect(screen.getByTestId('lt-events-ALPHA').textContent).toContain('large caps only');
    expect(screen.getByTestId('lt-host-ALPHA').textContent).toContain('Longs and shorts · 5% buy stop');
  });

  it('say what stops every host now, and link to the Bots page when the switch is there', async () => {
    resetNavRailStoreForTests();
    current = view({ can_trade: { ok: false, code: 'LT_BOT_OFF', why: 'the Bot switch is off: turn it on to let the hosts\' bots trade' } });
    await renderCard();
    expect(screen.getByTestId('lt-blocker').textContent).toContain('the Bot switch is off');
    fireEvent.click(screen.getByTestId('lt-open-bots'));
    expect(getNavPage()).toBe('bots');
  });

  it('link no page the Bots page cannot fix: the desk venue, a book that cannot be written', async () => {
    current = view({ can_trade: { ok: false, code: 'LT_VENUE', why: 'the desk is on Live: the Live Trader bot trades Paper only' } });
    await renderCard();
    expect(screen.getByTestId('lt-blocker').textContent).toContain('trades Paper only');
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();
    cleanup();
    _resetLiveTraderPollsForTests();
    current = view({ book_error: 'the holdings file cannot be written', can_trade: { ok: false, code: 'LT_BOT_OFF',
      why: 'the holdings file cannot be written' } });
    await renderCard();
    expect(screen.getByTestId('lt-blocker')).toBeTruthy();
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();
  });

  it('ask before a key turns off while its bot holds positions, and send nothing on "Keep it on"', async () => {
    confirmApp.mockImplementation(async () => false);
    await renderCard();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-key-ALPHA')); });
    await flush();
    expect(confirmApp).toHaveBeenCalledTimes(1);
    const opts = (confirmApp.mock.calls[0] as unknown as [{ message: string; confirmLabel: string }])[0];
    expect(opts.message).toContain('XYZ 4 shares');
    expect(opts.confirmLabel).toBe('Sell 1 and turn off');
    expect(writes).toEqual([]);
    confirmApp.mockImplementation(async () => true);
    await act(async () => { fireEvent.click(screen.getByTestId('lt-key-ALPHA')); });
    await flush();
    expect(writes).toEqual([{ url: expect.stringContaining('/api/bot/live-traders/ALPHA'), method: 'PATCH', body: { key: false } }]);
  });

  it('turn a key on with no question, and change who enters', async () => {
    current = view({ hosts: [host({ settings: { ...host().settings, key: false }, positions: [] })] });
    await renderCard();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-key-ALPHA')); });
    await flush();
    expect(confirmApp).not.toHaveBeenCalled();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-entry-ALPHA-you')); });
    await flush();
    expect(writes.map(w => w.body)).toEqual([{ key: true }, { entry: 'you' }]);
  });

  it('answer an ask on the card', async () => {
    current = view({ hosts: [host({ name: 'BRAVO', asks: [ask()] })] });
    await renderCard();
    await act(async () => { fireEvent.click(screen.getByTestId('lt-ask-approve-bravo-3')); });
    await flush();
    expect(writes).toEqual([{ url: expect.stringContaining('/api/bot/live-traders/BRAVO/asks/bravo-3'), method: 'POST',
      body: { approve: true } }]);
  });

  it('edit the money rules in place', async () => {
    await renderCard();
    fireEvent.click(screen.getByTestId('lt-change-ALPHA'));
    await act(async () => { fireEvent.click(screen.getByTestId('lt-edit-adds-ALPHA-4')); });
    await flush();
    const step = screen.getByTestId('lt-edit-step_usd-ALPHA');
    fireEvent.change(step, { target: { value: '250' } });
    await act(async () => { fireEvent.blur(step); });
    await flush();
    expect(writes.map(w => w.body)).toEqual([{ adds: 4 }, { step_usd: 250 }]);
  });

  it('say a write the backend refused', async () => {
    await renderCard();
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: { reason: 'LIVE_TRADER_INVALID', error: 'step_usd is a number from 50 to 10000' } }, 400)));
    fireEvent.click(screen.getByTestId('lt-change-ALPHA'));
    const step = screen.getByTestId('lt-edit-step_usd-ALPHA');
    fireEvent.change(step, { target: { value: '5' } });
    await act(async () => { fireEvent.blur(step); });
    await flush();
    expect(screen.getByTestId('lt-error').textContent).toContain('step_usd is a number from 50 to 10000');
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
  it('asks before it turns off while the Live Trader bot holds positions', async () => {
    const { useBotArm } = await import('./useBotArm');
    asksNow = { asks: [], held: [{ host: 'ALPHA', symbol: 'XYZ', side: 'long', qty: 4, state: 'open' }] };
    confirmApp.mockImplementation(async () => false);
    const { result } = renderHook(() => useBotArm());
    await act(async () => { await result.current.onSwitch(false); });
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect((confirmApp.mock.calls[0] as unknown as [{ message: string }])[0].message).toContain('XYZ 4 shares');
    expect(setSwitch).not.toHaveBeenCalled();
    confirmApp.mockImplementation(async () => true);
    await act(async () => { await result.current.onSwitch(false); });
    expect(setSwitch).toHaveBeenCalledWith(false);
  });

  it('never asks on Sim or Live: the Live Trader bot trades Paper only', async () => {
    const { useBotArm } = await import('./useBotArm');
    asksNow = { asks: [], held: [{ host: 'ALPHA', symbol: 'XYZ', side: 'long', qty: 4, state: 'open' }] };
    botSession.level_venue = 'sim';
    const { result } = renderHook(() => useBotArm());
    await act(async () => { await result.current.onSwitch(false); });
    botSession.level_venue = 'paper';
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
