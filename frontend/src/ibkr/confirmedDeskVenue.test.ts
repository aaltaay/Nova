/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DESK_POLL_CONFIRMED_VENUE_SHARE,
  DESK_POLL_SNAP_KEY_PREFIX,
  IBKR_STATUS_SESSION_KEY,
} from '../constantGroups/global_bar';
import { _resetDeskPollShareForTests, publishDeskPollSnap } from './deskSharedPoll';
import {
  _resetConfirmedDeskVenueStoreForTests,
  confirmDeskVenue,
  getConfirmedDeskVenueStoreSnapshot,
} from './confirmedDeskVenueStore';
import { getConfirmedDeskVenueSnapshot, subscribeConfirmedDeskVenue } from './confirmedDeskVenue';
import {
  _resetIbkrStatusPollerForTests,
  _setIbkrStatusPollerFetchForTests,
  getIbkrStatusSnapshot,
  pollIbkrStatusOnce,
} from './ibkrStatusPoller';

const ok = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
const status = (venue?: string) => ({ enabled: true, connected: true, mode: 'paper', venue });
const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };

function remote(venue: string, generation: string, revision: number) {
  const key = `${DESK_POLL_SNAP_KEY_PREFIX}${DESK_POLL_CONFIRMED_VENUE_SHARE}`;
  const newValue = JSON.stringify({ ts: Date.now(), payload: { schema_version: 1, venue, generation, revision } });
  localStorage.setItem(key, newValue);
  window.dispatchEvent(new StorageEvent('storage', { key, newValue }));
}

describe('confirmed desk venue', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
    localStorage.clear();
    sessionStorage.clear();
    _resetIbkrStatusPollerForTests();
    _resetConfirmedDeskVenueStoreForTests();
    _resetDeskPollShareForTests();
  });

  afterEach(() => {
    _resetIbkrStatusPollerForTests();
    _resetConfirmedDeskVenueStoreForTests();
    _resetDeskPollShareForTests();
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('cached status/share and legacy Gateway mode do not establish a venue', async () => {
    sessionStorage.setItem(IBKR_STATUS_SESSION_KEY, JSON.stringify(status('paper')));
    publishDeskPollSnap(DESK_POLL_CONFIRMED_VENUE_SHARE, {
      schema_version: 1, venue: 'paper', generation: 'cached', revision: Date.now(),
    });
    _resetIbkrStatusPollerForTests();
    _setIbkrStatusPollerFetchForTests(vi.fn(async () => ok(status())));
    const off = subscribeConfirmedDeskVenue(() => {});
    expect(getConfirmedDeskVenueSnapshot().venue).toBeNull();
    await flush();
    expect(getConfirmedDeskVenueSnapshot().venue).toBeNull();
    off();
  });

  it('a fresh explicit Live venue wins on the legacy paper Gateway', async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn(async () => ok(status('live'))));
    await pollIbkrStatusOnce();
    expect(getConfirmedDeskVenueSnapshot()).toMatchObject({ venue: 'live', generation: expect.any(String) });
    const before = getConfirmedDeskVenueSnapshot();
    await pollIbkrStatusOnce();
    expect(getConfirmedDeskVenueSnapshot()).toBe(before);
  });

  it('queues a new status read instead of letting an older GET undo a confirmed POST', async () => {
    confirmDeskVenue('paper');
    let release!: (reply: Response) => void;
    const fetcher = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { release = resolve; }))
      .mockResolvedValue(ok(status('live')));
    _setIbkrStatusPollerFetchForTests(fetcher);
    const old = pollIbkrStatusOnce();
    confirmDeskVenue('live');
    release(ok(status('paper')));
    await old;
    await flush();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(getConfirmedDeskVenueSnapshot().venue).toBe('live');
    expect(getIbkrStatusSnapshot().venue).toBe('live');
  });

  it('receives confirmed transitions across windows and gives ABA a distinct token', async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn(async () => ok(status('paper'))));
    const off = subscribeConfirmedDeskVenue(() => {});
    await flush();
    const first = getConfirmedDeskVenueSnapshot();
    const peerRevision = Date.now() + 20;
    // Hold the refresh so the shared confirmation can be inspected immediately.
    _setIbkrStatusPollerFetchForTests(vi.fn(() => new Promise<Response>(() => {})));
    remote('live', 'peer-live', peerRevision);
    expect(getConfirmedDeskVenueSnapshot()).toEqual({ venue: 'live', generation: 'peer-live' });
    expect(getIbkrStatusSnapshot()).toMatchObject({ venue: 'live', connected: false, stale: true });
    remote('paper', 'peer-paper', peerRevision + 1);
    expect(getConfirmedDeskVenueSnapshot()).toEqual({ venue: 'paper', generation: 'peer-paper' });
    expect(getConfirmedDeskVenueSnapshot().generation).not.toBe(first.generation);
    remote('live', 'old-peer-live', peerRevision);
    expect(getConfirmedDeskVenueSnapshot().generation).toBe('peer-paper');
    off();
  });

  it('does not turn sample status into a real venue confirmation', async () => {
    window.history.replaceState({}, '', '/?view=sample');
    const fetcher = vi.fn(async () => ok(status('paper')));
    _setIbkrStatusPollerFetchForTests(fetcher);
    const off = subscribeConfirmedDeskVenue(() => {});
    await pollIbkrStatusOnce();
    confirmDeskVenue('paper');
    expect(fetcher).not.toHaveBeenCalled();
    expect(getConfirmedDeskVenueSnapshot().venue).toBeNull();
    expect(getConfirmedDeskVenueStoreSnapshot().venue).toBeNull();
    off();
  });

  it.each([false, true])('rejects a real status finishing after entering sample (return to real: %s)', async (returnToReal) => {
    let release!: (reply: Response) => void;
    const fetcher = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { release = resolve; }))
      .mockResolvedValue(ok(status('live')));
    _setIbkrStatusPollerFetchForTests(fetcher);
    const old = pollIbkrStatusOnce();
    window.history.replaceState({}, '', '/?view=sample');
    window.dispatchEvent(new PopStateEvent('popstate'));
    if (returnToReal) {
      window.history.replaceState({}, '', '/');
      window.dispatchEvent(new PopStateEvent('popstate'));
    }
    release(ok(status('paper')));
    await old;
    expect(getConfirmedDeskVenueStoreSnapshot().venue).not.toBe('paper');
    await flush();
    expect(getConfirmedDeskVenueSnapshot().venue).toBe(returnToReal ? 'live' : null);
    expect(fetcher).toHaveBeenCalledTimes(returnToReal ? 2 : 1);
  });
});
