/**
 * @vitest-environment jsdom
 */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWhyMoving } from './useWhyMoving';

/** A replay read as of `at`; the backend stamps `generated_at` with the playhead it read at. */
function readAt(at: number) {
  return {
    schema_version: 1, symbol: 'SDEV', generated_at: at, rules_version: 'move-rules-v4', replay: true,
    likely: { kind: 'unexplained', label: `read at ${at}`, detail: null, confidence: 'likely' },
    checks: [],
  };
}

/** fetch answered by hand: each call waits until the test resolves it with the read at that playhead. */
function manualFetch() {
  const calls: Array<(at: number) => void> = [];
  const fetchMock = vi.fn(() => new Promise<Response>((resolve) => {
    calls.push((at) => resolve(new Response(JSON.stringify(readAt(at)), { status: 200 })));
  }));
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useWhyMoving on a Sim replay', () => {
  it('drops the read and reads again when the playhead goes back', async () => {
    const { fetchMock, calls } = manualFetch();
    const { result, rerender } = renderHook(({ at }) => useWhyMoving('SDEV', at), { initialProps: { at: 1000 } });
    await act(async () => calls[0](1000));
    await waitFor(() => expect(result.current.read?.generated_at).toBe(1000));

    rerender({ at: 900 });   // a rewind: the 1000 read holds facts from after 900

    expect(result.current.read).toBeNull();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await act(async () => calls[1](900));
    await waitFor(() => expect(result.current.read?.generated_at).toBe(900));
  });

  it('throws away an answer that was in flight across a rewind', async () => {
    const { fetchMock, calls } = manualFetch();
    const { result, rerender } = renderHook(({ at }) => useWhyMoving('SDEV', at), { initialProps: { at: 1000 } });

    rerender({ at: 900 });   // rewound while the 1000 read is still on its way
    await act(async () => calls[0](1000));

    expect(result.current.read).toBeNull();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await act(async () => calls[1](900));
    await waitFor(() => expect(result.current.read?.generated_at).toBe(900));
  });

  it('reads again once the playhead plays a minute past the last read, not before', async () => {
    const { fetchMock, calls } = manualFetch();
    const { result, rerender } = renderHook(({ at }) => useWhyMoving('SDEV', at), { initialProps: { at: 1000 } });
    await act(async () => calls[0](1000));
    await waitFor(() => expect(result.current.read?.generated_at).toBe(1000));

    rerender({ at: 1030 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.read?.generated_at).toBe(1000);   // playing forward keeps the earlier read
    rerender({ at: 1060 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
