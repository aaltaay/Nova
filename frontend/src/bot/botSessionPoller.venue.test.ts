/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DeskVenue } from '../constantGroups/desk_venue';
import { DESK_POLL_BOT_SHARE, DESK_POLL_SNAP_KEY_PREFIX } from '../constantGroups/global_bar';
import { getConfirmedDeskVenueSnapshot } from '../ibkr';
import { _resetDeskPollShareForTests } from '../ibkr/deskSharedPoll';
import { _resetConfirmedDeskVenueStoreForTests, confirmDeskVenue } from '../ibkr/confirmedDeskVenueStore';
import { _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests } from '../ibkr/ibkrStatusPoller';
import {
  _resetBotSessionPollerForTests,
  getBotSessionSnapshot,
  pollBotSessionOnce,
  runBotSessionWrite,
  subscribeBotSession,
} from './botSessionPoller';
import { strategySession } from './botsPageFixtures';
import * as api from './api';
import { toggleBotStock } from './useBotAllowlist';
import { useBotSession } from './useBotSession';
import type { BotSession } from './types';

vi.mock('./api', () => ({
  fetchBotSession: vi.fn(), fetchBotProposals: vi.fn(), fetchBotAudit: vi.fn(),
  postBotAllowlist: vi.fn(), patchBotSession: vi.fn(), armBotSession: vi.fn(),
  disarmBotSession: vi.fn(), switchBotSession: vi.fn(), resolveProposal: vi.fn(),
}));

const flush = async () => { for (let i = 0; i < 16; i += 1) await Promise.resolve(); };
const session = (venue: DeskVenue, symbol = venue.toUpperCase()) => strategySession({
  level_venue: venue, symbol_allowlist: [symbol],
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function share(payload: unknown) {
  const key = `${DESK_POLL_SNAP_KEY_PREFIX}${DESK_POLL_BOT_SHARE}`;
  const newValue = JSON.stringify({ ts: Date.now(), payload });
  localStorage.setItem(key, newValue);
  window.dispatchEvent(new StorageEvent('storage', { key, newValue }));
}

describe('venue-scoped bot snapshots', () => {
  let venue: DeskVenue;

  beforeEach(() => {
    _resetBotSessionPollerForTests();
    _resetIbkrStatusPollerForTests();
    _resetConfirmedDeskVenueStoreForTests();
    _resetDeskPollShareForTests();
    localStorage.clear();
    sessionStorage.clear();
    vi.clearAllMocks();
    venue = 'paper';
    _setIbkrStatusPollerFetchForTests(vi.fn(async () => ({
      ok: true, json: async () => ({ enabled: true, connected: true, mode: 'paper', venue }),
    }) as Response));
    vi.mocked(api.fetchBotSession).mockImplementation(async () => session(venue));
    vi.mocked(api.fetchBotProposals).mockResolvedValue([]);
    vi.mocked(api.fetchBotAudit).mockResolvedValue([]);
    confirmDeskVenue(venue);
  });

  afterEach(() => {
    _resetBotSessionPollerForTests();
    _resetIbkrStatusPollerForTests();
    _resetConfirmedDeskVenueStoreForTests();
    _resetDeskPollShareForTests();
    window.history.replaceState({}, '', '/');
  });

  function switchTo(next: DeskVenue) {
    venue = next;
    confirmDeskVenue(next);
  }

  it('clears old state immediately and queues refresh behind an older read', async () => {
    const off = subscribeBotSession(() => {});
    await flush();
    expect(getBotSessionSnapshot().session?.level_venue).toBe('paper');
    const old = deferred<BotSession>();
    vi.mocked(api.fetchBotSession).mockImplementationOnce(() => old.promise);
    const reading = pollBotSessionOnce();
    switchTo('live');
    expect(getBotSessionSnapshot()).toMatchObject({ session: null, proposals: [], audit: [], error: null });
    expect(api.fetchBotSession).toHaveBeenCalledTimes(2);
    old.resolve(session('paper', 'OLD'));
    await reading;
    await flush();
    expect(api.fetchBotSession).toHaveBeenCalledTimes(3);
    expect(getBotSessionSnapshot().session).toMatchObject({ level_venue: 'live', symbol_allowlist: ['LIVE'] });
    off();
  });

  it('rejects an old Paper read even after Paper → Live → Paper', async () => {
    const off = subscribeBotSession(() => {});
    await flush();
    const firstScope = getConfirmedDeskVenueSnapshot();
    const old = deferred<BotSession>();
    const fresh = deferred<BotSession>();
    vi.mocked(api.fetchBotSession)
      .mockImplementationOnce(() => old.promise)
      .mockImplementationOnce(() => fresh.promise);
    const reading = pollBotSessionOnce();
    switchTo('live');
    switchTo('paper');
    expect(getConfirmedDeskVenueSnapshot().generation).not.toBe(firstScope.generation);
    old.resolve(session('paper', 'OLD'));
    await reading;
    await flush();
    expect(getBotSessionSnapshot().session).toBeNull();
    fresh.resolve(session('paper', 'FRESH'));
    await flush();
    expect(getBotSessionSnapshot().session?.symbol_allowlist).toEqual(['FRESH']);
    off();
  });

  it('rejects old-generation, foreign-venue and legacy unscoped window shares', async () => {
    const off = subscribeBotSession(() => {});
    await flush();
    const oldScope = getConfirmedDeskVenueSnapshot();
    switchTo('live');
    switchTo('paper');
    await flush();
    const scope = getConfirmedDeskVenueSnapshot();
    const snap = { session: session('paper', 'OLD'), proposals: [], audit: [], error: null, errorSticky: false };
    share({ schema_version: 1, scope: oldScope, snap });
    share({ schema_version: 1, scope, snap: { ...snap, session: session('live', 'FOREIGN') } });
    share(snap);
    expect(getBotSessionSnapshot().session?.symbol_allowlist).toEqual(['PAPER']);
    share({ schema_version: 1, scope, snap: { ...snap, session: session('paper', 'PEER') } });
    expect(getBotSessionSnapshot().session?.symbol_allowlist).toEqual(['PEER']);
    off();
  });

  it('does not hand an old allowlist write result to its UI caller', async () => {
    const off = subscribeBotSession(() => {});
    await flush();
    const old = deferred<BotSession>();
    vi.mocked(api.postBotAllowlist).mockReturnValueOnce(old.promise);
    const writing = toggleBotStock('OLD', 'add', true);
    switchTo('live');
    await flush();
    old.resolve(session('paper', 'OLD'));
    expect(await writing).toEqual({ session: null, error: null });
    expect(getBotSessionSnapshot().session?.level_venue).toBe('live');
    off();
  });

  it('does not stick an old mutation failure on the new venue through useBotSession', async () => {
    const { result, unmount } = renderHook(() => useBotSession());
    await act(flush);
    const old = deferred<BotSession>();
    vi.mocked(api.patchBotSession).mockReturnValueOnce(old.promise);
    let writing!: Promise<BotSession | null>;
    act(() => { writing = result.current.patch({ level: 1 }); });
    await act(async () => { switchTo('live'); await flush(); });
    await act(async () => {
      old.reject(new Error('Paper refused this patch'));
      expect(await writing).toBeNull();
    });
    expect(result.current.error).toBeNull();
    expect(result.current.session?.level_venue).toBe('live');
    expect(result.current.busy).toBe(false);
    unmount();
  });

  it('refuses unstamped or foreign sessions and keeps queued refresh failure on the current venue', async () => {
    const off = subscribeBotSession(() => {});
    await flush();
    const old = deferred<BotSession>();
    vi.mocked(api.fetchBotSession)
      .mockImplementationOnce(() => old.promise)
      .mockRejectedValueOnce(new Error('Live read failed'));
    const reading = pollBotSessionOnce();
    switchTo('live');
    old.resolve(session('paper'));
    await reading;
    await flush();
    expect(getBotSessionSnapshot()).toMatchObject({ session: null, error: 'Live read failed' });
    await runBotSessionWrite(async () => session('paper', 'FOREIGN'));
    expect(getBotSessionSnapshot().session).toBeNull();
    off();
  });

  it('does not render a session while the explicit venue is unknown', async () => {
    confirmDeskVenue(undefined);
    await pollBotSessionOnce();
    expect(getBotSessionSnapshot().session).toBeNull();
  });

  it('does not apply a direct write after a real → sample → real visit', async () => {
    const old = deferred<BotSession>();
    const writing = runBotSessionWrite(() => old.promise);
    window.history.replaceState({}, '', '/?view=sample');
    window.dispatchEvent(new PopStateEvent('popstate'));
    window.history.replaceState({}, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
    old.resolve(session('paper', 'OLD'));
    expect(await writing).toBeNull();
    expect(getBotSessionSnapshot().session).toBeNull();
  });

  it('does not publish a direct read that visited sample before its reply', async () => {
    const old = deferred<BotSession>();
    vi.mocked(api.fetchBotSession).mockImplementationOnce(() => old.promise);
    const reading = pollBotSessionOnce();
    window.history.replaceState({}, '', '/?view=sample');
    window.dispatchEvent(new PopStateEvent('popstate'));
    window.history.replaceState({}, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
    old.resolve(session('paper', 'OLD'));
    await reading;
    expect(getBotSessionSnapshot().session).toBeNull();
    expect(localStorage.getItem(`${DESK_POLL_SNAP_KEY_PREFIX}${DESK_POLL_BOT_SHARE}`)).toBeNull();
  });
});
