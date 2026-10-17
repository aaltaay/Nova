/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SIM_CLOCK_SCRUB_EVENT } from '../sim';
import { VP_RETRY_MS } from './volumeProfileConstants';

const fetchVolumeProfile = vi.fn();
vi.mock('./volumeProfileApi', () => ({ fetchVolumeProfile: (...a: unknown[]) => fetchVolumeProfile(...a) }));

import { useProfileAnswer, useSessionAnchor } from './useProfileAnswer';

describe('a profile the desk asks for', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    fetchVolumeProfile.mockReset();
  });

  it('asks again after the backend did not answer, even with no refresh of its own', async () => {
    const drawn = { profile: null, filling: false, error: 'no bars' };
    fetchVolumeProfile.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(drawn);
    const { result } = renderHook(() => useProfileAnswer('yesterday', 'AAPL', true, '2026-09-30', null, 0));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe('the backend did not answer');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(VP_RETRY_MS);
    });
    expect(fetchVolumeProfile).toHaveBeenCalledTimes(2);
    expect(result.current).toEqual(drawn);
  });

  it("drops today's profile on a Sim scrub and asks again, cancelling the request in flight", async () => {
    const before = { profile: null, filling: false, error: 'before the scrub', feed: 'massive' };
    const after = { profile: null, filling: false, error: 'after the scrub', feed: 'massive' };
    const signals: AbortSignal[] = [];
    fetchVolumeProfile.mockImplementation((...a: unknown[]) => {
      signals.push(a[4] as AbortSignal);
      return Promise.resolve(signals.length === 1 ? before : after);
    });
    const { result } = renderHook(() => useProfileAnswer('today', 'AAPL', true, '2026-09-10', 1789047000, 0));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.error).toBe('before the scrub');
    await act(async () => {
      window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT, { detail: { symbol: 'MSFT' } }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchVolumeProfile).toHaveBeenCalledTimes(1);         // another stock's scrub
    await act(async () => {
      window.dispatchEvent(new CustomEvent(SIM_CLOCK_SCRUB_EVENT, { detail: { symbol: 'AAPL' } }));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(signals[0].aborted).toBe(true);
    expect(fetchVolumeProfile).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBe('after the scrub');
  });

  it('asks again when the pane\'s candles change', async () => {
    fetchVolumeProfile.mockResolvedValue({ profile: null, filling: false, error: 'x', feed: null });
    const { rerender } = renderHook(({ rev }) => useProfileAnswer('today', 'AAPL', true, '2026-09-10', 1789047000, 0, rev),
      { initialProps: { rev: 1 } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    rerender({ rev: 2 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetchVolumeProfile).toHaveBeenCalledTimes(2);
  });
});

describe("today's anchor", () => {
  it('goes back to 09:30 when the pane moves to another day or stock', () => {
    const { result, rerender } = renderHook(({ symbol, day }) => useSessionAnchor(symbol, day), {
      initialProps: { symbol: 'AAPL', day: '2026-09-30' as string | null },
    });
    act(() => result.current[1](1790779500));
    expect(result.current[0]).toBe(1790779500);
    rerender({ symbol: 'AAPL', day: '2026-10-01' });
    expect(result.current[0]).toBeNull();
    act(() => result.current[1](1790866800));
    rerender({ symbol: 'MSFT', day: '2026-10-01' });
    expect(result.current[0]).toBeNull();
  });

  it('does not come back when the pane returns to the day or stock it was dragged on', () => {
    const { result, rerender } = renderHook(({ symbol, day }) => useSessionAnchor(symbol, day), {
      initialProps: { symbol: 'AAPL', day: '2026-09-30' as string | null },
    });
    act(() => result.current[1](1790779500));
    rerender({ symbol: 'AAPL', day: '2026-10-01' });
    rerender({ symbol: 'AAPL', day: '2026-09-30' });
    expect(result.current[0]).toBeNull();
    act(() => result.current[1](1790779500));
    rerender({ symbol: 'MSFT', day: '2026-09-30' });
    rerender({ symbol: 'AAPL', day: '2026-09-30' });
    expect(result.current[0]).toBeNull();
  });
});
