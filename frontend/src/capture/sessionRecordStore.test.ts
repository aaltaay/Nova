/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IBKR_STATUS_SESSION_KEY } from '../constants';
import { CAPTURE_STATUS_FRESH_MS } from './constants';
import {
  getRecordingSymbols, getSessionRecordError, isTabRecording, recordingSymbolsIn,
  startTabRecord, stopTabRecord, subscribeSessionRecord,
} from './sessionRecordStore';
import {
  _resetIbkrStatusPollerForTests, _setIbkrStatusPollerFetchForTests,
  pollIbkrStatusOnce,
} from '../ibkr/ibkrStatusPoller';

const command = vi.hoisted(() => vi.fn());
vi.mock('../api/novaFetch', () => ({ novaFetch: command }));
const state = (symbol: string | null) => ({
  mode: 'paper', connected: false, enabled: true,
  capture: !!symbol, recording: !!symbol, capture_symbol: symbol,
});
const response = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response;
let unsubscribe: (() => void) | undefined;

beforeEach(async () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-09-20T12:00:00Z'));
  sessionStorage.removeItem(IBKR_STATUS_SESSION_KEY);
  _resetIbkrStatusPollerForTests();
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response(state(null))));
  command.mockResolvedValue(response({ capture: false }));
  await stopTabRecord('AAPL');
  await Promise.resolve();
  command.mockClear();
});
afterEach(() => {
  unsubscribe?.();
  unsubscribe = undefined;
  _resetIbkrStatusPollerForTests();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
async function poll(symbol: string | null) {
  _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response(state(symbol))));
  await pollIbkrStatusOnce();
}

describe('server-owned recording store', () => {
  it('has one owner, follows external changes and backend restart', async () => {
    await poll('aapl');
    expect(getRecordingSymbols()).toEqual(['AAPL']);
    expect(isTabRecording(' aapl ')).toBe(true);
    await poll('TSLA');
    expect(getRecordingSymbols()).toEqual(['TSLA']);
    expect(isTabRecording('AAPL')).toBe(false);
    await poll(null);
    expect(getRecordingSymbols()).toEqual([]);
  });
  it('does not trust a persisted recording on reload', async () => {
    sessionStorage.setItem(IBKR_STATUS_SESSION_KEY, JSON.stringify(state('AAPL')));
    _resetIbkrStatusPollerForTests();
    expect(getRecordingSymbols()).toEqual([]);
    await poll('AAPL');
    expect(getRecordingSymbols()).toEqual(['AAPL']);
  });
  it.each(['http', 'network'])('fails open on the first %s poll error and recovers', async kind => {
    await poll('AAPL');
    _setIbkrStatusPollerFetchForTests(kind === 'http'
      ? vi.fn().mockResolvedValue(response({}, false))
      : vi.fn().mockRejectedValue(new Error('offline')));
    await pollIbkrStatusOnce();
    expect(getRecordingSymbols()).toEqual([]);
    expect(getSessionRecordError()).toMatch(/request failed/);
    await poll('TSLA');
    expect(getRecordingSymbols()).toEqual(['TSLA']);
    expect(getSessionRecordError()).toBeNull();
  });
  it('expires and notifies subscribers while a subsequent poll hangs', async () => {
    await poll('AAPL');
    _setIbkrStatusPollerFetchForTests(vi.fn(() => new Promise<Response>(() => {})));
    const listener = vi.fn();
    unsubscribe = subscribeSessionRecord(listener);
    listener.mockClear();
    await vi.advanceTimersByTimeAsync(CAPTURE_STATUS_FRESH_MS);
    expect(getRecordingSymbols()).toEqual([]);
    expect(listener).toHaveBeenCalled();
    expect(getSessionRecordError()).toMatch(/stale/);
    expect(console.warn).toHaveBeenCalledWith('session Record:', 'Recording status is stale');
  });
  it('never adds a requested owner optimistically, even after successful POST', async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn(() => new Promise<Response>(() => {})));
    command.mockResolvedValue(response({ capture: true, capture_symbol: 'AAPL' }));
    expect(await startTabRecord(' aapl ')).toBeNull();
    expect(getRecordingSymbols()).toEqual([]);
    expect(JSON.parse(command.mock.calls[0][1].body)).toEqual({ enabled: true, symbol: 'AAPL' });
  });
  it('never clears a known owner optimistically and surfaces stop errors', async () => {
    await poll('AAPL');
    _setIbkrStatusPollerFetchForTests(vi.fn(() => new Promise<Response>(() => {})));
    command.mockResolvedValue(response({ capture: false }));
    expect(await stopTabRecord('AAPL')).toBeNull();
    expect(getRecordingSymbols()).toEqual(['AAPL']);
    command.mockResolvedValue(response({ capture: true, error: 'Recorder stop failed' }));
    expect(await stopTabRecord('AAPL')).toBe('Recorder stop failed');
    expect(getSessionRecordError()).toBe('Recorder stop failed');
  });
  it('exposes and logs ownership conflicts and network failures', async () => {
    command.mockResolvedValue(response({ detail: 'Already recording AAPL; stop it first' }, false));
    expect(await startTabRecord('TSLA')).toMatch(/Already recording AAPL/);
    expect(console.warn).toHaveBeenCalled();
    command.mockRejectedValue(new Error('offline'));
    expect(await stopTabRecord('AAPL')).toMatch(/Could not reach Nova/);
  });
  it('exposes a recorder failure reported by the status endpoint', async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response({
      ...state(null), capture_error: 'disk full',
    })));
    await pollIbkrStatusOnce();
    expect(getSessionRecordError()).toBe('disk full');
    expect(getRecordingSymbols()).toEqual([]);
  });

  it('reads recording symbols only from a list of strings (C14)', () => {
    expect(recordingSymbolsIn({ capture_symbols: 'GRML' })).toEqual([]);
    expect(recordingSymbolsIn({ capture_symbols: 'GRML', capture_symbol: 'grml' })).toEqual(['GRML']);
    expect(recordingSymbolsIn({ capture_symbols: [' gdc ', 7, null, 'IMCC'] })).toEqual(['GDC', 'IMCC']);
    expect(recordingSymbolsIn({})).toEqual([]);
  });

  it('a status with capture_symbols as a string records nothing rather than crashing', async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response({
      mode: 'paper', connected: false, enabled: true, capture: true, recording: true, capture_symbols: 'GRML',
    })));
    await pollIbkrStatusOnce();
    expect(getRecordingSymbols()).toEqual([]);
  });

  it('a text/plain 500 to Record says Nova answered, never that it could not be reached (C65)', async () => {
    command.mockResolvedValue({ ok: false, status: 500, text: async () => 'Internal Server Error' } as Response);
    expect(await startTabRecord('GRML')).toBe('Nova answered 500 to Record start: Internal Server Error');
    command.mockResolvedValue({ ok: false, status: 502, text: async () => '<html>Bad Gateway</html>' } as Response);
    expect(await stopTabRecord('GRML')).toBe('Nova answered 502 to Record stop');
    command.mockRejectedValue(new TypeError('Failed to fetch'));
    expect(await stopTabRecord('GRML')).toMatch(/Could not reach Nova/);
  });

  it("names each symbol's own trouble: B's menu never shows A's tape or command error (C55)", async () => {
    _setIbkrStatusPollerFetchForTests(vi.fn().mockResolvedValue(response({
      ...state(null), capture: true, recording: true, capture_symbols: ['AAA', 'BBB'],
      capture_error: 'IBKR AllLast stale; no recent prints for AAA',
      capture_errors: { AAA: 'IBKR AllLast stale; no recent prints for AAA' },
    })));
    await pollIbkrStatusOnce();
    expect(getSessionRecordError('AAA')).toMatch(/for AAA/);
    expect(getSessionRecordError('BBB')).toBeNull();
    // The legacy single value is unchanged for readers that name no symbol.
    expect(getSessionRecordError()).toMatch(/for AAA/);
    command.mockResolvedValue(response({ detail: 'Already recording 3 symbols' }, false));
    await startTabRecord('CCC');
    expect(getSessionRecordError('CCC')).toMatch(/Already recording/);
    expect(getSessionRecordError('BBB')).toBeNull();
  });
});
