/**
 * @vitest-environment jsdom
 *
 * Bot API shapes (QA C12 / C70) and the sample desk's bot doors (V4).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SAMPLE_BOT_ABSENT, SAMPLE_WRITE_REFUSAL } from '../sample_data/sampleCopy';
import {
  armBotSession,
  fetchBotAudit,
  fetchBotProposals,
  fetchBotSession,
  patchBotSession,
  postBotAllowlist,
  syncTraderLive,
} from './api';
import { parseBotSession } from './botPayload';
import { _resetBotSessionPollerForTests, getBotSessionSnapshot, pollBotSessionOnce, runBotSessionWrite } from './botSessionPoller';

const SESSION = {
  level: 0, armed: false, strategy: null, brain_session_id: null,
  caps: { max_shares: 1, bp_budget_usd: 50, working_ttl_sec: 3, extended_hours: false, allowlist: [] },
  advise: { enabled: false, usd_cap: 2, call_cap: 10, usd_spent: 0, calls_used: 0 },
  soft_breaker_fired: false, hard_lock_until_date: null, day_lock_active: false,
  focus: [], trader_live: ['GRML'], working: [],
};

function answer(body: unknown, init: { ok?: boolean; status?: number; unreadable?: boolean } = {}) {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => {
      if (init.unreadable) throw new SyntaxError('Unexpected token <');
      return body;
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
  _resetBotSessionPollerForTests();
});

describe('bot answers the page cannot render are refused, not rendered (C12 / C70)', () => {
  it('a sound session passes; one without caps or advise, a list or null does not', () => {
    expect(parseBotSession(SESSION)).toMatchObject({ caps: { max_shares: 1 }, trader_live: ['GRML'] });
    expect(parseBotSession({ ...SESSION, caps: undefined })).toBeNull();
    expect(parseBotSession({ ...SESSION, advise: null })).toBeNull();
    expect(parseBotSession([])).toBeNull();
    expect(parseBotSession(null)).toBeNull();
    expect(parseBotSession({ ...SESSION, trader_live: 'GRML' })?.trader_live).toEqual([]);
  });

  it.each([
    ['an unreadable 200', answer(null, { unreadable: true })],
    ['an empty object', answer({})],
    ['a JSON list', answer([])],
    ['JSON null', answer(null)],
  ])('%s on /session, /proposals and /audit names the endpoint and the status', async (_label, reply) => {
    vi.stubGlobal('fetch', vi.fn(async () => reply));
    await expect(fetchBotSession()).rejects.toThrow('Bot session: Nova answered an unreadable response (HTTP 200)');
    await expect(fetchBotProposals()).rejects.toThrow('Bot proposals: Nova answered an unreadable response (HTTP 200)');
    await expect(fetchBotAudit()).rejects.toThrow('Bot audit: Nova answered an unreadable response (HTTP 200)');
  });

  it('the poller keeps a message, never a raw JS error, and never a broken session', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (String(url).includes('/proposals') ? answer(null) : answer(SESSION))));
    await pollBotSessionOnce();
    const snap = getBotSessionSnapshot();
    expect(snap.session).toBeNull();
    expect(snap.error).toBe('Bot proposals: Nova answered an unreadable response (HTTP 200)');
    expect(snap.error).not.toMatch(/Cannot read properties/);
  });

  it('a write answer without a session shape is refused, never applied', async () => {
    await expect(runBotSessionWrite(async () => ({ symbol_allowlist: ['X'] }) as never)).rejects.toThrow(/unreadable/);
    expect(getBotSessionSnapshot().session).toBeNull();
  });
});

describe('the sample desk has no bot (V4)', () => {
  it('refuses every bot write before any request', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    window.history.replaceState({}, '', '/?view=sample');
    await expect(postBotAllowlist('SMPL', 'add')).rejects.toThrow(SAMPLE_WRITE_REFUSAL);
    await expect(patchBotSession({ level: 1 })).rejects.toThrow(SAMPLE_WRITE_REFUSAL);
    await expect(armBotSession()).rejects.toThrow(SAMPLE_WRITE_REFUSAL);
    await syncTraderLive([]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('the poller asks nothing and states the absence', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    window.history.replaceState({}, '', '/?view=sample');
    await pollBotSessionOnce();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(getBotSessionSnapshot()).toMatchObject({ session: null, error: SAMPLE_BOT_ABSENT });
  });
});
