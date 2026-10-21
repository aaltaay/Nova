/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import answerPending from './__fixtures__/answer_pending.json';
import answerReady from './__fixtures__/answer_ready.json';
import answerWarming from './__fixtures__/answer_warming.json';
import { AHEAD_SLOW_RETRY_MS, AHEAD_STALE_READY_MAX_TRIES } from './aheadConstants';
import type { AheadAnswer } from './aheadTypes';

const SCRUB = 'nova:sim-clock-scrub';
const desk = { replay: false, playhead: null as number | null };
vi.mock('../sim', () => ({
  SIM_CLOCK_SCRUB_EVENT: 'nova:sim-clock-scrub',
  matchesSimClockScrub: (e: Event, sym: string) => {
    const d = (e as CustomEvent<{ symbol?: string } | undefined>).detail;
    return !d?.symbol || d.symbol.toUpperCase() === sym.toUpperCase();
  },
  useSimReplayDesk: () => desk.replay,
  useSimReplayPlayhead: () => desk.playhead,
}));
const fetchAhead = vi.fn();
vi.mock('./aheadApi', () => ({ fetchAhead: (...a: unknown[]) => fetchAhead(...a) }));

import { aheadPollerRefs } from './aheadPoller';
import { aheadHeldOf, resetAheadStoreForTesting } from './aheadStore';
import { useAheadAnswer } from './useAheadAnswer';

const ready = answerReady as unknown as AheadAnswer;
const pending = answerPending as unknown as AheadAnswer;
const warming = answerWarming as unknown as AheadAnswer;
/** The fixtures' desk clock: 5 s into the minute their forecast starts at. */
const T0 = 1792500065_000;

const flush = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

describe("a pane's Ahead answer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(T0);
    desk.replay = false;
    desk.playhead = null;
    resetAheadStoreForTesting();
  });
  afterEach(() => {
    vi.useRealTimers();
    fetchAhead.mockReset();
  });

  it('asks nothing at all while switched off', async () => {
    const { result } = renderHook(() => useAheadAnswer('XYZ', false));
    await flush(120_000);
    expect(fetchAhead).not.toHaveBeenCalled();
    expect(result.current).toEqual({ answer: null, fetchProblem: null });
  });

  it('asks at once, then not again until the minute rolls over, then 1.5 s after it', async () => {
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    const { result, unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    expect(result.current.answer).toBe(ready);
    await flush(54_000);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    await flush(1_000); // 09:xx:00 -- the candle has just closed
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    await flush(2_000);
    expect(fetchAhead).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('on a stock with no trade in the minute that closed, asks a few times, then waits for the next minute', async () => {
    // Every answer stays the one for the minute before: no newer candle exists to forecast from.
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    const { unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    await flush(60_000); // the minute rolled 5 s ago
    expect(fetchAhead).toHaveBeenCalledTimes(1 + AHEAD_STALE_READY_MAX_TRIES);
    await flush(45_000); // still that minute: not one ask more
    expect(fetchAhead).toHaveBeenCalledTimes(1 + AHEAD_STALE_READY_MAX_TRIES);
    await flush(15_000); // the next minute rolled
    expect(fetchAhead.mock.calls.length).toBeGreaterThan(1 + AHEAD_STALE_READY_MAX_TRIES);
    expect(fetchAhead.mock.calls.length).toBeLessThanOrEqual(1 + 2 * AHEAD_STALE_READY_MAX_TRIES);
    unmount();
  });

  it('asks again after retry_ms while the backend reads the minute, and draws nothing kept from before', async () => {
    fetchAhead.mockResolvedValueOnce({ answer: pending, problem: null }).mockResolvedValue({ answer: ready, problem: null });
    const { result, unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    expect(result.current.answer?.ai.state).toBe('pending');
    await flush(1_500);
    expect(fetchAhead).toHaveBeenCalledTimes(2);
    expect(result.current.answer?.ai.state).toBe('ready');
    unmount();
  });

  it('asks every 15 s while the forecaster is warming', async () => {
    fetchAhead.mockResolvedValue({ answer: warming, problem: null });
    const { unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    await flush(AHEAD_SLOW_RETRY_MS - 1_000);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    await flush(1_000);
    expect(fetchAhead).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('keeps the words of a failed read and asks again slowly', async () => {
    fetchAhead.mockResolvedValue({ answer: null, problem: 'restart the API' });
    const { result, unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    expect(result.current).toEqual({ answer: null, fetchProblem: 'restart the API' });
    await flush(AHEAD_SLOW_RETRY_MS);
    expect(fetchAhead).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('shares one poller between panes and stops it with the last one', async () => {
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    const a = renderHook(() => useAheadAnswer('XYZ', true));
    const b = renderHook(() => useAheadAnswer('xyz', true));
    await flush(0);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    expect(aheadPollerRefs('XYZ')).toBe(2);
    a.unmount();
    expect(aheadPollerRefs('XYZ')).toBe(1);
    b.unmount();
    expect(aheadPollerRefs('XYZ')).toBe(0);
    expect(aheadHeldOf('XYZ').answer).toBeNull();
  });

  it('asks nothing while the window is hidden', async () => {
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
    const { unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(30_000);
    expect(fetchAhead).not.toHaveBeenCalled();
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    await flush(1_000);
    expect(fetchAhead).toHaveBeenCalledTimes(1);
    unmount();
  });

  it('drops the answer on a scrub of its symbol and asks at once', async () => {
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    const { result, unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    fetchAhead.mockReturnValueOnce(new Promise(() => {}));
    act(() => {
      window.dispatchEvent(new CustomEvent(SCRUB, { detail: { symbol: 'ABC' } }));
    });
    expect(result.current.answer).toBe(ready);
    act(() => {
      window.dispatchEvent(new CustomEvent(SCRUB, { detail: { symbol: 'XYZ' } }));
    });
    expect(result.current.answer).toBeNull();
    expect(fetchAhead).toHaveBeenCalledTimes(2);
    unmount();
  });

  it('after a rewind, drops an answer made after the playhead', async () => {
    desk.replay = true;
    desk.playhead = 1792500065;
    fetchAhead.mockResolvedValue({ answer: ready, problem: null });
    const { result, rerender, unmount } = renderHook(() => useAheadAnswer('XYZ', true));
    await flush(0);
    expect(result.current.answer).toBe(ready);
    desk.playhead = 1792499000; // rewound about 18 minutes
    rerender();
    act(() => {
      window.dispatchEvent(new CustomEvent(SCRUB, { detail: { symbol: 'XYZ' } }));
    });
    await flush(0);
    expect(result.current.answer).toBeNull();
    unmount();
  });
});
