/**
 * @vitest-environment jsdom
 *
 * Status poller findings from the QA sweep of 2026-09-22: a failed poll
 * withdraws the recording claims (C23) and names what failed (C58); a
 * malformed body is shaped, not trusted (C1 / C4); the sample desk makes no
 * request and reads only the sample status (V4).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import { SAMPLE_IBKR_STATUS } from '../sample_data/sampleStatus';
import {
  _resetIbkrStatusPollerForTests,
  _setIbkrStatusPollerFetchForTests,
  _setIbkrStatusPollerNowForTests,
  getIbkrStatusSnapshot,
  pollIbkrStatusOnce,
  subscribeIbkrStatus,
} from './ibkrStatusPoller';

const RECORDING = {
  enabled: true,
  connected: true,
  mode: 'sim',
  venue: 'sim',
  capture: true,
  recording: true,
  capture_symbol: 'GDC',
  capture_symbols: ['GDC', 'IMCC'],
  capture_sessions: [{ symbol: 'GDC' }, { symbol: 'IMCC' }],
  capture_resume: [{ symbol: 'IMCC', pending: true }],
  capture_stopped: [{ symbol: 'GRML', at: 1, reason: 'failure', resumed: false }],
};

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;

describe('ibkrStatusPoller (QA batch)', () => {
  beforeEach(() => {
    sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
    window.history.replaceState({}, '', '/');
    _resetIbkrStatusPollerForTests();
    _setIbkrStatusPollerNowForTests(() => 1_700_000_000_000);
  });

  afterEach(() => {
    _resetIbkrStatusPollerForTests();
    window.history.replaceState({}, '', '/');
  });

  it('withdraws "Recording: GDC, IMCC" when the status stops answering (C23)', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn().mockResolvedValueOnce(ok(RECORDING)).mockResolvedValueOnce({ ok: false, status: 500 } as Response),
    );
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().capture_symbols).toEqual(['GDC', 'IMCC']);
    await pollIbkrStatusOnce();
    const snap = getIbkrStatusSnapshot();
    expect(snap.stale).toBe(true);
    expect(snap.capture).toBe(false);
    expect(snap.recording).toBe(false);
    expect(snap.capture_symbols).toEqual([]);
    expect(snap.capture_sessions).toEqual([]);
    expect(snap.capture_resume).toEqual([]);
    // A stop that happened is still a fact; the toast is not a present-tense claim.
    expect(snap.capture_stopped).toHaveLength(1);
  });

  it('says what failed: the status route, not the Gateway (C58)', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn()
        .mockResolvedValueOnce({ ok: false, status: 500 } as Response)
        .mockRejectedValueOnce(new Error('down'))
        .mockResolvedValueOnce(ok(RECORDING)),
    );
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().statusError).toBe('HTTP 500');
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().statusError).toBe('no answer');
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().statusError).toBeNull();
  });

  it('shapes a malformed body instead of crashing the header (C1 / C4)', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn().mockResolvedValueOnce(ok({ ...RECORDING, capture_stopped: { symbol: 'GRML' }, account_id: 5 })),
    );
    await pollIbkrStatusOnce();
    const snap = getIbkrStatusSnapshot();
    expect(snap.capture_stopped).toEqual([]);
    expect(snap.account_id).toBeNull();
  });

  it('an unreadable 200 is a failed poll, not a status', async () => {
    _setIbkrStatusPollerFetchForTests(
      vi.fn().mockResolvedValueOnce({ ok: true, status: 200, json: async () => { throw new SyntaxError('html'); } } as unknown as Response),
    );
    await pollIbkrStatusOnce();
    expect(getIbkrStatusSnapshot().stale).toBe(true);
    expect(getIbkrStatusSnapshot().statusError).toBe('unreadable response');
  });

  it('on the sample desk reads the sample status and asks the backend nothing (V4)', async () => {
    const fetchSpy = vi.fn(async () => ok(RECORDING));
    _setIbkrStatusPollerFetchForTests(fetchSpy);
    window.history.replaceState({}, '', '/?view=sample');
    const off = subscribeIbkrStatus(() => {});
    await pollIbkrStatusOnce();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(getIbkrStatusSnapshot()).toBe(SAMPLE_IBKR_STATUS);
    off();
  });

  it('leaving the sample desk polls the live status again at once', async () => {
    const fetchSpy = vi.fn(async () => ok(RECORDING));
    _setIbkrStatusPollerFetchForTests(fetchSpy);
    window.history.replaceState({}, '', '/?view=sample');
    const listener = vi.fn();
    const off = subscribeIbkrStatus(listener);
    fetchSpy.mockClear();
    window.history.replaceState({}, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
    await Promise.resolve();
    await Promise.resolve();
    expect(listener).toHaveBeenCalled();
    expect(fetchSpy).toHaveBeenCalled();
    off();
  });
});
