/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
});
