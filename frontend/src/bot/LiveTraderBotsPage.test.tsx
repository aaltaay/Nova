/**
 * @vitest-environment jsdom
 *
 * Bots > LiveTrader Bots (operator decision 2026-10-15): the LiveTrader Bots key on top, the Live Traders panel under
 * it, the key turning the family off and on in one press -- off, the hosts' bots cannot place orders or sell -- and
 * Bots itself, empty for now. Made-up hosts.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetBotSessionPollerForTests } from './botSessionPoller';
import { BotsGroupPage } from './BotsGroupPage';
import { botsFetchRouter, keysView, strategySession } from './botsPageFixtures';
import { _resetLiveTraderPollsForTests } from './liveTraderStore';
import { LiveTraderBotsPage } from './LiveTraderBotsPage';

vi.mock('../followed_traders', () => ({ useFollowedTradersEnabled: () => true }));

const NOW = Date.now() / 1000;
const CARDS = {
  schema_version: 1, generated_at: NOW, enabled: true, venue: 'paper', desk_venue: 'paper',
  can_trade: { ok: false, code: 'LT_FAMILY_OFF',
    why: 'the LiveTrader Bots key is off: turn it on at the top of Bots > LiveTrader Bots: its bots place no order, not even a sell' },
  sell_all_at: '15:55', sell_all_ts: null,
  watcher: { running: true, pass_ts: NOW, idle: true, text: 'Idle: no host\'s key is on',
    feed: { state: 'ok', error: null, read_age_sec: 2, behind_sec: 3, bar_visible: true, live: true } },
  settings_error: null, book_error: null, hosts: [], defaults: {}, bounds: {},
};

beforeEach(() => {
  _resetBotSessionPollerForTests();
  _resetDeskPollShareForTests();
  _resetLiveTraderPollsForTests();
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
  it('puts its family key on top of the Live Traders panel, and says the key above stops the hosts', async () => {
    const fetchMock = mockFetch(false);
    render(<LiveTraderBotsPage />);
    await flush();
    const key = screen.getByTestId('bot-key-live_trader');
    const panel = screen.getByTestId('bots-live-traders');
    expect(key.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId('bot-key-live_trader-switch').getAttribute('aria-checked')).toBe('false');
    expect(screen.getByTestId('bot-key-live_trader-line').textContent).toBe("Off: bots can't place orders or sell.");
    expect(screen.getByTestId('lt-blocker').textContent).toContain('the LiveTrader Bots key is off');
    expect(screen.queryByTestId('lt-open-bots')).toBeNull();      // no switch on another page to go to
    await act(async () => { fireEvent.click(screen.getByTestId('bot-key-live_trader-switch')); });
    await flush();
    const bodies = fetchMock.mock.calls.filter(([url]) => String(url).includes('/session/keys'))
      .map(([, init]) => String((init as RequestInit | undefined)?.body ?? ''));
    expect(bodies).toEqual(['{"family":"live_trader","on":true}']);
    expect(screen.getByTestId('bot-key-live_trader-line').textContent).toBe('On: LiveTrader Bots may place orders on Paper.');
  });
});

describe('Bots', () => {
  it('is empty for now: it points at its two children', () => {
    render(<BotsGroupPage />);
    expect(screen.getByTestId('bots-group-page').textContent).toBe('BotsOpen LiveTrader Bots or Strategy Bots on the left.');
  });
});
