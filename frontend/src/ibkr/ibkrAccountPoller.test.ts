/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  _ibkrAccountPollerDebugForTests,
  _resetIbkrAccountPollerForTests,
  configureIbkrAccountPoller,
  subscribeIbkrAccount,
} from './ibkrAccountPoller';
import { _resetDeskPollShareForTests } from './deskSharedPoll';

describe('ibkrAccountPoller', () => {
  beforeEach(() => {
    _resetDeskPollShareForTests();
    _resetIbkrAccountPollerForTests();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/account')) {
          return {
            ok: true,
            json: async () => ({ connected: true, mode: 'paper', NetLiquidation: 42 }),
          };
        }
        if (String(url).includes('/positions')) {
          return { ok: true, json: async () => [{ symbol: 'DAIC', qty: 1 }] };
        }
        return { ok: true, json: async () => [] };
      }),
    );
  });

  afterEach(() => {
    _resetIbkrAccountPollerForTests();
    _resetDeskPollShareForTests();
    vi.unstubAllGlobals();
  });

  it('one interval serves two subscribers', async () => {
    configureIbkrAccountPoller({ connected: true, sample: false });
    const a = vi.fn();
    const b = vi.fn();
    const offA = subscribeIbkrAccount(a);
    const offB = subscribeIbkrAccount(b);
    expect(_ibkrAccountPollerDebugForTests().subscriberCount).toBe(2);
    expect(_ibkrAccountPollerDebugForTests().timerOn).toBe(true);
    await Promise.resolve();
    await Promise.resolve();
    const accountCalls = vi.mocked(fetch).mock.calls.filter((c) =>
      String(c[0]).includes('/account'),
    );
    expect(accountCalls.length).toBe(1);
    offA();
    expect(_ibkrAccountPollerDebugForTests().timerOn).toBe(true);
    offB();
    expect(_ibkrAccountPollerDebugForTests().subscriberCount).toBe(0);
    expect(_ibkrAccountPollerDebugForTests().timerOn).toBe(false);
  });
});
