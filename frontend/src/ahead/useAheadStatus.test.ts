/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import statusReady from './__fixtures__/status_ready.json';
import { AHEAD_STATUS_POLL_MS } from './aheadConstants';

const fetchAheadStatus = vi.fn();
vi.mock('./aheadApi', () => ({ fetchAheadStatus: (...a: unknown[]) => fetchAheadStatus(...a) }));

import { useAheadStatus } from './useAheadStatus';

describe("the forecaster's status for the panel", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    fetchAheadStatus.mockReset();
  });

  it('asks nothing while the panel is closed', async () => {
    renderHook(() => useAheadStatus(false));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AHEAD_STATUS_POLL_MS * 2);
    });
    expect(fetchAheadStatus).not.toHaveBeenCalled();
  });

  it('reads it at once and every 30 s while open, and says why when it cannot be read', async () => {
    fetchAheadStatus.mockResolvedValueOnce({ status: statusReady, problem: null })
      .mockResolvedValueOnce({ status: null, problem: 'no API' });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useAheadStatus(true));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current).toEqual({ status: statusReady, problem: null });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AHEAD_STATUS_POLL_MS);
    });
    expect(fetchAheadStatus).toHaveBeenCalledTimes(2);
    expect(result.current).toEqual({ status: null, problem: 'no API' });
    unmount();
    warn.mockRestore();
  });
});
