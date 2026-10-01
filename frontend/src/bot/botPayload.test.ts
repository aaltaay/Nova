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
  it('a sound session passes; one without caps, a list or null does not', () => {
    expect(parseBotSession(SESSION)).toMatchObject({ caps: { max_shares: 1 }, trader_live: ['GRML'] });
    expect(parseBotSession({ ...SESSION, caps: undefined })).toBeNull();
    expect(parseBotSession([])).toBeNull();
    expect(parseBotSession(null)).toBeNull();
    expect(parseBotSession({ ...SESSION, trader_live: 'GRML' })?.trader_live).toEqual([]);
    // ADR 042 K: the advise budget is retired; an older backend that still sends one parses the same.
    expect(parseBotSession({ ...SESSION, advise: { enabled: false } })).not.toBeNull();
  });

  it('folds each ADR 042 name and its legacy alias both ways, so no reader sees one without the other', () => {
    expect(parseBotSession({ ...SESSION, armed: true })).toMatchObject({ active: true, armed: true });
    expect(parseBotSession({ ...SESSION, active: true, armed: false })).toMatchObject({ active: true, armed: true });
    expect(parseBotSession({ ...SESSION, live_fire_ready: true })).toMatchObject({ ready: true, live_fire_ready: true });
    expect(parseBotSession({ ...SESSION, ready: false, live_fire_ready: true })).toMatchObject({ ready: false, live_fire_ready: false });
    const kinds = parseBotSession({ ...SESSION, caps: { ...SESSION.caps, allowlist: ['buy_market'] } });
    expect(kinds?.caps).toMatchObject({ api_kinds: ['buy_market'], allowlist: ['buy_market'] });
    const legacy = parseBotSession({ ...SESSION, day_lock_active: true, hard_lock_until_date: '2026-09-30' });
    expect(legacy?.day_lock).toEqual({ active: true, until: '2026-09-30', tripped_at: null, pnl: null, venue: null });
    const lock = { active: true, until: '2026-10-01T04:00:00-04:00', tripped_at: 1_790_000_000, pnl: -212.4, venue: 'paper' };
    expect(parseBotSession({ ...SESSION, day_lock: lock })).toMatchObject({ day_lock: lock, day_lock_active: true });
    expect(parseBotSession({ ...SESSION, deactivated: { at: 5, reason: 'restart', text: 'Not active -- the backend restarted' } })?.deactivated)
      .toEqual({ at: 5, reason: 'restart', text: 'Not active -- the backend restarted' });
    expect(parseBotSession({ ...SESSION, deactivated: { at: 5 } })?.deactivated).toBeNull();
    expect(parseBotSession({ ...SESSION, entries_today: { count: 1, cap: 1, venue_day: 'd', entries: 'x' } })?.entries_today)
      .toEqual({ count: 1, cap: 1, venue_day: 'd', entries: [], approved: 0 });
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
