/**
 * No bot turns on while the desk padlock is locked (operator decision 2026-10-20): every bot's On -- a TraderTV
 * host's Bot key, a family key, a strategy set On, the Bot switch, Activate -- asks the one question over the
 * backend's `BOT_PADLOCK_LOCKED`, unlocks only on yes, and presses again.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BOT_PADLOCK_KEPT_OFF, BOT_PADLOCK_PROMPT_TITLE } from '../constantGroups/bot';
import { armBotSession, patchBotSession, setBotFamilyKey, switchBotSession } from './api';
import { patchLiveTrader } from './liveTraderApi';

const confirmApp = vi.fn(async (_opts: unknown) => true);
vi.mock('../ux/appDialogApi', () => ({ confirmApp: (opts: unknown) => confirmApp(opts) }));

type Call = { url: string; method: string; body: string };
let calls: Call[] = [];

/** The first bot write is refused for the padlock; the unlock and every write after it go through. */
function stubBackend(): void {
  let refused = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const call = { url: String(url), method: init?.method ?? 'GET', body: String(init?.body ?? '') };
    calls.push(call);
    if (call.url.includes('/ibkr/')) return { ok: true, status: 200, json: async () => ({}) };
    if (!refused && call.method !== 'GET') {
      refused = true;
      return { ok: false, status: 409, json: async () => ({ detail: { reason: 'BOT_PADLOCK_LOCKED', error: 'the desk padlock is locked' } }) };
    }
    return { ok: true, status: 200, json: async () => ({ hosts: [], level: 2 }) };
  }));
}

const arms = () => calls.filter(c => c.url.includes('/ibkr/arm')).map(c => c.body);
const writes = () => calls.filter(c => !c.url.includes('/ibkr/') && c.method !== 'GET');

beforeEach(() => {
  calls = [];
  confirmApp.mockClear();
  stubBackend();
});

afterEach(() => vi.unstubAllGlobals());

describe('every bot asks to unlock the padlock before it turns on', () => {
  it.each([
    ['a TraderTV host\'s Bot key', () => patchLiveTrader('NEAL', { key: true })],
    ['the LiveTrader Bots key', () => setBotFamilyKey('live_trader', true)],
    ['the Strategy Bots key', () => setBotFamilyKey('strategy', true)],
    ['a strategy set On', () => patchBotSession({ setup_levels: { first_pullback: 2 } })],
    ['the Bot switch', () => switchBotSession(true)],
    ['Activate', () => armBotSession()],
  ])('%s: yes unlocks the padlock and presses again', async (_name, press) => {
    await press();
    expect(confirmApp).toHaveBeenCalledTimes(1);
    expect(confirmApp.mock.calls[0][0]).toMatchObject({ title: BOT_PADLOCK_PROMPT_TITLE });
    expect(arms()).toEqual(['{"armed":true,"actor":"operator"}']);
    expect(writes()).toHaveLength(2);
    expect(writes()[1].body).toBe(writes()[0].body);
  });

  it('Keep it off unlocks nothing and turns nothing on', async () => {
    confirmApp.mockImplementationOnce(async () => false);
    await expect(patchLiveTrader('NEAL', { key: true })).rejects.toThrow(BOT_PADLOCK_KEPT_OFF);
    expect(arms()).toEqual([]);
    expect(writes()).toHaveLength(1);
  });

  it('a refusal for another reason never asks', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false, status: 409, json: async () => ({ detail: { reason: 'BOT_LIVE_NOT_BUILT', error: 'Live trading by a bot is not built' } }),
    })));
    await expect(switchBotSession(true)).rejects.toThrow('Live trading by a bot is not built');
    expect(confirmApp).not.toHaveBeenCalled();
  });
});
