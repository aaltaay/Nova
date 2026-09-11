/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import {
  _ibkrStatusPollerDebugForTests,
  _resetIbkrStatusPollerForTests,
  _setIbkrStatusPollerFetchForTests,
  _setIbkrStatusPollerNowForTests,
  getIbkrStatusSnapshot,
  pollIbkrStatusOnce,
  subscribeIbkrStatus,
} from './ibkrStatusPoller';

const connectedPayload = {
  enabled: true,
  connected: true,
  transport_connected: true,
  session_reason: 'ok',
  mode: 'paper',
  orders_enabled: true,
  spend_status: 'paper_armed',
};

function jsonOk(body: unknown) {
  return {
    ok: true,
    json: async () => body,
  } as Response;
}

describe('ibkrStatusPoller', () => {
  beforeEach(() => {
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    _resetIbkrStatusPollerForTests();
    _setIbkrStatusPollerNowForTests(() => 1_700_000_000_000);
  });

  afterEach(() => {
    _resetIbkrStatusPollerForTests();
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
  });

  it('one interval serves two subscribers', () => {
    const a = vi.fn();
    const b = vi.fn();
    _setIbkrStatusPollerFetchForTests(vi.fn(async () => jsonOk(connectedPayload)));
    const offA = subscribeIbkrStatus(a);
    const offB = subscribeIbkrStatus(b);
    expect(_ibkrStatusPollerDebugForTests().subscriberCount).toBe(2);
    expect(_ibkrStatusPollerDebugForTests().timerOn).toBe(true);
    offA();
    expect(_ibkrStatusPollerDebugForTests().timerOn).toBe(true);
    offB();
    expect(_ibkrStatusPollerDebugForTests().subscriberCount).toBe(0);
    expect(_ibkrStatusPollerDebugForTests().timerOn).toBe(false);
  });

  it('a failed poll clears connected and stamps stale_since', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn()
        .mockResolvedValueOnce(jsonOk(connectedPayload))
        .mockRejectedValueOnce(new Error('down')),
    );
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().connected).toBe(true);
    expect(getIbkrStatusSnapshot().stale).toBe(false);

    await pollIbkrStatusOnce();
    const snap = getIbkrStatusSnapshot();
    expect(snap.connected).toBe(false);
    expect(snap.transport_connected).toBe(false);
    expect(snap.stale).toBe(true);
    expect(snap.staleSince).toBe(1_700_000_000_000);
    expect(snap.mode).toBe('paper');
  });

  it('skips a stacked poll while one is in flight', async () => {
    let release!: (value: Response) => void;
    const hung = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const fetchFn = vi.fn(() => hung);
    _setIbkrStatusPollerFetchForTests(fetchFn as unknown as typeof fetch);

    const first = pollIbkrStatusOnce();
    await Promise.resolve();
    expect(_ibkrStatusPollerDebugForTests().inflight).toBe(true);

    await pollIbkrStatusOnce();
    expect(fetchFn).toHaveBeenCalledTimes(1);

    release(jsonOk(connectedPayload));
    await first;
    await Promise.resolve();
    expect(getIbkrStatusSnapshot().connected).toBe(true);
  });

  it('persists disconnected after N consecutive misses', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn()
        .mockResolvedValueOnce(jsonOk(connectedPayload))
        .mockRejectedValue(new Error('down')),
    );
    await pollIbkrStatusOnce();
    await pollIbkrStatusOnce();
    expect(JSON.parse(sessionStorage.getItem(IBKR_STATUS_SESSION_KEY) ?? '{}').connected).toBe(
      true,
    );
    await pollIbkrStatusOnce();
    const stored = JSON.parse(sessionStorage.getItem(IBKR_STATUS_SESSION_KEY) ?? '{}');
    expect(stored.connected).toBe(false);
  });
});
