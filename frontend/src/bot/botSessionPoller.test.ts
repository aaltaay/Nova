/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  _botSessionPollerDebugForTests,
  _resetBotSessionPollerForTests,
  subscribeBotSession,
  voteBotPollInterval,
} from './botSessionPoller';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';

describe('botSessionPoller', () => {
  beforeEach(() => {
    _resetDeskPollShareForTests();
    _resetBotSessionPollerForTests();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const href = String(url);
        if (href.includes('/proposals')) return { ok: true, json: async () => ({ proposals: [] }) };
        if (href.includes('/audit')) return { ok: true, json: async () => ({ entries: [] }) };
        return {
          ok: true,
          json: async () => ({
            level: 0,
            armed: false,
            strategy: null,
            caps: {
              max_shares: 1,
              bp_budget_usd: 50,
              working_ttl_sec: 3,
              extended_hours: false,
              allowlist: [],
            },
            advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
            soft_breaker_fired: false,
            hard_lock_until_date: null,
            day_lock_active: false,
            focus: [],
            trader_live: [],
            working: [],
            brain_session_id: null,
          }),
        };
      }),
    );
  });

  afterEach(() => {
    _resetBotSessionPollerForTests();
    _resetDeskPollShareForTests();
    vi.unstubAllGlobals();
  });

  it('one fetch serves two subscribers and only armed voters keep the interval', async () => {
    const offA = subscribeBotSession(() => {});
    const offB = subscribeBotSession(() => {});
    expect(_botSessionPollerDebugForTests().subscriberCount).toBe(2);
    await Promise.resolve();
    await Promise.resolve();
    const sessionCalls = vi.mocked(fetch).mock.calls.filter((c) =>
      String(c[0]).includes('/bot/session') && !String(c[0]).includes('arm'),
    );
    expect(sessionCalls.length).toBe(1);
    expect(_botSessionPollerDebugForTests().timerOn).toBe(false);
    const unvote = voteBotPollInterval(2_500);
    expect(_botSessionPollerDebugForTests().timerOn).toBe(true);
    unvote();
    expect(_botSessionPollerDebugForTests().timerOn).toBe(false);
    offA();
    offB();
    expect(_botSessionPollerDebugForTests().subscriberCount).toBe(0);
  });
});
