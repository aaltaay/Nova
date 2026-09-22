/**
 * @vitest-environment jsdom
 */
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useHodMomoDebugPoll } from './useHodMomoDebugPoll';

function PollProbe({ onReady }: { onReady: (api: ReturnType<typeof useHodMomoDebugPoll>) => void }) {
  const api = useHodMomoDebugPoll();
  useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

describe('useHodMomoDebugPoll', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('counters')) {
          return { ok: true, json: async () => ({ ticks: 1 }) };
        }
        if (String(url).includes('recent')) {
          return { ok: true, json: async () => ({ decisions: [] }) };
        }
        if (String(url).includes('snaps')) {
          return { ok: true, json: async () => ({ snaps: [] }) };
        }
        return { ok: false, json: async () => ({}) };
      }),
    );
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('starts polling on mount and stops after unmount', async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    await act(async () => {
      root.render(<PollProbe onReady={() => undefined} />);
    });
    const initialCalls = fetchMock.mock.calls.length;
    expect(initialCalls).toBeGreaterThanOrEqual(3);

    await act(async () => {
      root.unmount();
    });
    const afterUnmount = fetchMock.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(fetchMock.mock.calls.length).toBe(afterUnmount);
  });

  it('keeps the counters age the time since the last answer, never epoch seconds (QA W15)', async () => {
    vi.setSystemTime(new Date('2026-09-22T09:00:00Z'));
    let latest: ReturnType<typeof useHodMomoDebugPoll> | null = null;
    await act(async () => {
      root.render(<PollProbe onReady={(api) => { latest = api; }} />);
    });
    const ages: number[] = [];
    for (let i = 0; i < 6; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
      ages.push(latest!.countersAge);
    }
    expect(Math.max(...ages)).toBeLessThan(5);
  });
});
