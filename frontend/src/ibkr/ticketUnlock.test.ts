/**
 * @vitest-environment jsdom
 *
 * The padlock has one source of truth: the backend arm latch, read from the
 * one status poller every window shares. Nothing is kept per tab.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import {
  _resetIbkrStatusPollerForTests,
  _setIbkrStatusPollerFetchForTests,
  pollIbkrStatusOnce,
} from './ibkrStatusPoller';
import {
  livePinMissing,
  lockTicketSession,
  readTicketSessionUnlocked,
  subscribeTicketSessionUnlock,
  unlockNeedsPin,
  unlockTicketSession,
} from './ticketUnlock';

/** A backend with a latch: status reports it, POST /api/ibkr/arm moves it. */
function fakeBackend(start: Record<string, unknown>) {
  const server: Record<string, unknown> = { connected: true, mode: 'paper', ...start };
  const posts: unknown[] = [];
  const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    if (String(url).endsWith('/api/ibkr/arm')) {
      const body = JSON.parse(String(init?.body));
      posts.push(body);
      server.armed = body.armed;
      return { ok: true, status: 200, json: async () => ({ armed: body.armed }) } as Response;
    }
    return { ok: true, status: 200, json: async () => ({ ...server }) } as Response;
  });
  return { server, posts, fetchMock };
}

describe('ticketUnlock', () => {
  beforeEach(() => {
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    _resetIbkrStatusPollerForTests();
  });

  afterEach(() => {
    _resetIbkrStatusPollerForTests();
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    vi.unstubAllGlobals();
  });

  it('starts locked and reads an unreported arm_requires_pin as Live', () => {
    expect(readTicketSessionUnlocked()).toBe(false);
    expect(unlockNeedsPin()).toBe(true);
    expect(livePinMissing()).toBe(false);
  });

  it('follows the status snapshot, and every reader sees the same answer', async () => {
    const backend = fakeBackend({ armed: false, arm_requires_pin: false });
    _setIbkrStatusPollerFetchForTests(backend.fetchMock as unknown as typeof fetch);
    const windowA: boolean[] = [];
    const windowB: boolean[] = [];
    const offA = subscribeTicketSessionUnlock(() => windowA.push(readTicketSessionUnlocked()));
    const offB = subscribeTicketSessionUnlock(() => windowB.push(readTicketSessionUnlocked()));
    const polled = async (armed: boolean) => {
      backend.server.armed = armed;
      void pollIbkrStatusOnce();
      await vi.waitFor(() => expect(windowA.at(-1)).toBe(armed));
    };

    await polled(false);
    expect(unlockNeedsPin()).toBe(false);
    // Armed from anywhere -- another window, a bot on Paper -- reads armed here.
    await polled(true);
    expect(readTicketSessionUnlocked()).toBe(true);
    // A backend restart disarms; the next poll re-locks, no click needed.
    await polled(false);
    expect(readTicketSessionUnlocked()).toBe(false);

    const changes = windowA.filter((v, i) => i === 0 || v !== windowA[i - 1]);
    expect(changes).toEqual([false, true, false]);
    expect(windowB).toEqual(windowA);
    offA();
    offB();
  });

  it('says so when the backend reports the Live PIN is not set', async () => {
    const backend = fakeBackend({ armed: false, arm_requires_pin: true, live_arm_pin_set: false });
    _setIbkrStatusPollerFetchForTests(backend.fetchMock as unknown as typeof fetch);
    await pollIbkrStatusOnce();
    expect(unlockNeedsPin()).toBe(true);
    expect(livePinMissing()).toBe(true);
  });

  it('unlock and lock go to the backend and leave no flag in browser storage', async () => {
    const backend = fakeBackend({ armed: false, arm_requires_pin: false });
    vi.stubGlobal('fetch', backend.fetchMock);
    sessionStorage.clear();
    localStorage.clear();

    await expect(unlockTicketSession()).resolves.toMatchObject({ ok: true });
    await vi.waitFor(() => expect(readTicketSessionUnlocked()).toBe(true));
    await expect(lockTicketSession()).resolves.toMatchObject({ ok: true });
    await vi.waitFor(() => expect(readTicketSessionUnlocked()).toBe(false));

    expect(backend.posts).toEqual([
      { armed: true, actor: 'operator' },
      { armed: false, actor: 'operator' },
    ]);
    const keys = [...Object.keys(sessionStorage), ...Object.keys(localStorage)];
    expect(keys.filter((k) => k !== IBKR_STATUS_SESSION_KEY)).toEqual([]);
  });
});
