/**
 * @vitest-environment jsdom
 *
 * Bots > LiveTrader Bots (operator, 2026-10-15: "i want all content from the original tradertv live to be inside
 * livetrader bots"): the followed traders' page with the LiveTrader Bots key in its head and each host's bot in their
 * card; the key turns the family off and on in one press -- off, the hosts' bots cannot place orders or sell -- and
 * Bots itself, empty for now. The page itself is a stand-in here (its own tests are followed_traders'); this checks
 * what the bots give it. Made-up hosts.
 */
import type React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FollowedSlots } from '../followed_traders';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsGroupPage } from './BotsGroupPage';
import { botsFetchRouter, keysView, strategySession } from './botsPageFixtures';
import { _resetLiveTraderPollsForTests } from './liveTraderStore';
import { LiveTraderBotsPage } from './LiveTraderBotsPage';

const opened = vi.fn();
vi.mock('../followed_traders', () => ({
  useFollowedTradersEnabled: () => true,
  FollowedTradersPage: ({ slots, onOpenTrader }: { slots: FollowedSlots; onOpenTrader?: (s: string) => void }) => {
    const { Head, Trader } = slots;
    return (
      <div data-testid="followed-page-stub">
        <h1>LiveTrader Bots</h1>
        {Head ? <Head /> : null}
        {Trader ? <Trader name="ALPHA" open={[]} /> : null}
        <button type="button" data-testid="open-xyz" onClick={() => onOpenTrader?.('XYZ')}>XYZ</button>
      </div>
    );
  },
}));

// The Scanner's account dock (Positions / Orders · today) wraps the page; its own tests are the scanner's.
vi.mock('../scanner', () => ({
  ScannerDesk: ({ children, host }: { children: React.ReactNode; host?: string }) => (
    <div data-testid="account-dock-stack" data-host={host}>{children}<div data-testid="positions-dock-stub" /></div>
  ),
}));

const NOW = Date.now() / 1000;
const CARDS = {
  schema_version: 1, generated_at: NOW, enabled: true, venue: 'paper', desk_venue: 'paper',
  can_trade: { ok: false, code: 'LT_FAMILY_OFF',
    why: 'the LiveTrader Bots key is off: turn it on beside the title: its bots place no order, not even a sell' },
  sell_all_at: '15:55', sell_all_ts: null,
  watcher: { running: true, pass_ts: NOW, idle: true, text: 'Idle: no host\'s key is on',
    feed: { state: 'ok', error: null, read_age_sec: 2, behind_sec: 3, bar_visible: true, live: true } },
  settings_error: null, book_error: null, defaults: {}, bounds: {},
  hosts: [{
    name: 'ALPHA', face: null, on_air: true, left_ts: null,
    settings: { key: false, entry: 'nova', exit: 'nova', step_usd: 500, adds: 2, allowance_usd: 2500, sides: 'both',
      short_stop_pct: 5, take_open: true, mode: 'bot' },
    state: { tone: 'warn', text: 'off' }, allowance: { used_usd: 0, of_usd: 2500 },
    today: { pl_usd: 0, realized_usd: 0, unrealized_usd: 0, trades: 0, skipped: 0, series: [] },
    positions: [], asks: [], events: [],
  }],
};

beforeEach(() => {
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  _resetLiveTraderPollsForTests();
  opened.mockClear();
});

afterEach(() => {
  cleanup();
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  _resetLiveTraderPollsForTests();
  vi.unstubAllGlobals();
});

async function flush() {
  for (let i = 0; i < 6; i += 1) await act(async () => { await Promise.resolve(); });
}

function mockFetch(live_trader = true) {
  const router = botsFetchRouter({ session: strategySession({ keys: keysView({ live_trader }) }) });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes('/bot/live-traders')) {
      return { ok: true, status: 200, json: async () => CARDS } as unknown as Response;
    }
    return router(url, init);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('LiveTrader Bots', () => {
  it("is the followed traders' page, its family key after the title, and says the key stops the hosts", async () => {
    const fetchMock = mockFetch(false);
    render(<LiveTraderBotsPage onOpenTrader={opened} />);
    await flush();
    const key = screen.getByTestId('bot-key-live_trader');
    expect(key.parentElement!.previousElementSibling!.textContent).toBe('LiveTrader Bots');
    expect(screen.getByTestId('lt-strip-ALPHA')).toBeTruthy();
    expect(screen.getByTestId('bot-key-live_trader-switch').getAttribute('aria-checked')).toBe('false');
    // The compact key: OFF on screen, its words on hover.
    const state = screen.getByTestId('bot-key-live_trader-line');
    expect(state.textContent).toBe('OFF');
    expect(state.getAttribute('data-tip')).toBe("Off: bots can't place orders or sell.");
    expect(screen.getByTestId('lt-blocker').textContent).toBe('No orders · the LiveTrader Bots key is off');
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();      // the key is right here
    await act(async () => { fireEvent.click(screen.getByTestId('bot-key-live_trader-switch')); });
    await flush();
    const bodies = fetchMock.mock.calls.filter(([url]) => String(url).includes('/session/keys'))
      .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));
    expect(bodies).toEqual(['{"family":"live_trader","on":true}']);
    expect(screen.getByTestId('bot-key-live_trader-line').textContent).toBe('ON');
    expect(screen.getByTestId('bot-key-live_trader-line').getAttribute('data-tip')).toBe('On: LiveTrader Bots may place orders on Paper.');
  });

  it('shows the Positions / Orders · today dock under the hosts (operator ask 2026-10-16)', async () => {
    mockFetch(false);
    render(<LiveTraderBotsPage onOpenTrader={opened} />);
    await flush();
    const stack = screen.getByTestId('account-dock-stack');
    expect(stack.getAttribute('data-host')).toBe('bots');
    expect(stack.contains(screen.getByTestId('followed-page-stub'))).toBe(true);
    expect(screen.getByTestId('positions-dock-stub')).toBeTruthy();
  });

  it('opens a ticker in the Trader through the desk', async () => {
    mockFetch();
    render(<LiveTraderBotsPage onOpenTrader={opened} />);
    await flush();
    fireEvent.click(screen.getByTestId('open-xyz'));
    expect(opened).toHaveBeenCalledWith('XYZ');
  });
});

describe('Bots', () => {
  it('is empty for now: it points at its two children', () => {
    render(<BotsGroupPage />);
    expect(screen.getByTestId('bots-group-page').textContent).toBe('BotsOpen LiveTrader Bots or Strategy Bots on the left.');
  });
});
