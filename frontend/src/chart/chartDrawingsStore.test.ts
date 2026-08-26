import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Time } from 'lightweight-charts';
import type { SerializedDrawing } from 'lightweight-charts-drawing';
import { CHART_DRAWINGS_SAVE_DEBOUNCE_MS } from '../constants';
import {
  clearDrawings,
  clearDrawingsStoreForTests,
  ensureDrawings,
  getDrawings,
  removeDrawing,
  subscribeDrawings,
  upsertDrawing,
} from './chartDrawingsStore';

function line(id: string, price = 231.5): SerializedDrawing {
  return {
    id,
    type: 'horizontal-line',
    anchors: [{ time: 1_756_000_000 as Time, price }],
    style: {},
    options: {},
  } as SerializedDrawing;
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  clearDrawingsStoreForTests();
  fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ symbol: 'AAPL', drawings: [] }),
  })) as unknown as ReturnType<typeof vi.fn>;
  vi.stubGlobal('fetch', fetchMock);
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function requestsOf(method: string): string[] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init?.method ?? 'GET') === method)
    .map(([url]) => String(url));
}

describe('chartDrawingsStore', () => {
  it('is symbol-scoped and case-insensitive', () => {
    upsertDrawing('aapl', line('a'));
    expect(getDrawings('AAPL')).toHaveLength(1);
    expect(getDrawings('TSLA')).toHaveLength(0);
  });

  it('notifies every subscriber on the same symbol -- this is what shares panes', () => {
    const paneOne = vi.fn();
    const paneTwo = vi.fn();
    subscribeDrawings('AAPL', paneOne);
    subscribeDrawings('AAPL', paneTwo);

    upsertDrawing('AAPL', line('a'));

    expect(paneOne).toHaveBeenCalledTimes(1);
    expect(paneTwo).toHaveBeenCalledTimes(1);
  });

  it('does not notify subscribers of a different symbol', () => {
    const other = vi.fn();
    subscribeDrawings('TSLA', other);
    upsertDrawing('AAPL', line('a'));
    expect(other).not.toHaveBeenCalled();
  });

  it('stops notifying after unsubscribe', () => {
    const pane = vi.fn();
    subscribeDrawings('AAPL', pane)();
    upsertDrawing('AAPL', line('a'));
    expect(pane).not.toHaveBeenCalled();
  });

  it('replaces a drawing in place when the id already exists', () => {
    upsertDrawing('AAPL', line('a', 100));
    upsertDrawing('AAPL', line('a', 200));
    const stored = getDrawings('AAPL');
    expect(stored).toHaveLength(1);
    expect(stored[0].anchors[0].price).toBe(200);
  });

  it('coalesces a drag burst into one PUT', async () => {
    for (let i = 0; i < 10; i += 1) upsertDrawing('AAPL', line('a', 100 + i));
    expect(requestsOf('PUT')).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);

    const puts = requestsOf('PUT');
    expect(puts).toHaveLength(1);
    const body = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(body.drawings[0].anchors[0].price).toBe(109);
  });

  it('removeDrawing persists the shorter list', async () => {
    upsertDrawing('AAPL', line('a'));
    upsertDrawing('AAPL', line('b'));
    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);

    removeDrawing('AAPL', 'a');
    expect(getDrawings('AAPL').map((d) => d.id)).toEqual(['b']);
    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);

    const body = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(body.drawings.map((d: SerializedDrawing) => d.id)).toEqual(['b']);
  });

  it('removeDrawing on an unknown id neither notifies nor saves', async () => {
    const pane = vi.fn();
    subscribeDrawings('AAPL', pane);
    removeDrawing('AAPL', 'ghost');
    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);
    expect(pane).not.toHaveBeenCalled();
    expect(requestsOf('PUT')).toHaveLength(0);
  });

  it('clearDrawings empties locally, DELETEs, and cancels a pending PUT', async () => {
    const pane = vi.fn();
    subscribeDrawings('AAPL', pane);
    upsertDrawing('AAPL', line('a'));

    clearDrawings('AAPL');

    expect(getDrawings('AAPL')).toEqual([]);
    expect(pane).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);
    expect(requestsOf('PUT')).toHaveLength(0);
    expect(requestsOf('DELETE')).toHaveLength(1);
  });

  it('ensureDrawings dedupes concurrent GETs for one symbol', async () => {
    const both = Promise.all([ensureDrawings('AAPL'), ensureDrawings('aapl')]);
    await vi.advanceTimersByTimeAsync(0);
    await both;
    expect(requestsOf('GET')).toHaveLength(1);
  });

  it('ensureDrawings publishes the fetched list to subscribers', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ symbol: 'AAPL', drawings: [line('server')] }),
    }));
    const pane = vi.fn();
    subscribeDrawings('AAPL', pane);

    await ensureDrawings('AAPL');

    expect(pane).toHaveBeenCalled();
    expect(getDrawings('AAPL').map((d) => d.id)).toEqual(['server']);
  });

  it('a failed GET keeps the cached list instead of blanking the chart', async () => {
    upsertDrawing('AAPL', line('local'));
    fetchMock.mockImplementation(async () => ({ ok: false, status: 503, json: async () => ({}) }));

    await expect(ensureDrawings('AAPL')).resolves.toHaveLength(1);
    expect(getDrawings('AAPL').map((d) => d.id)).toEqual(['local']);
  });

  it('an in-flight GET must not erase a line drawn while it was pending', async () => {
    // Reproduces the API-slow race: the operator draws, then a stale empty
    // server list lands and blanks the chart.
    let resolveGet: (value: unknown) => void = () => {};
    fetchMock.mockImplementation(
      (_url: string, init?: RequestInit) =>
        (init?.method === 'PUT' || init?.method === 'DELETE'
          ? Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
          : new Promise((resolve) => { resolveGet = resolve; })),
    );

    const pending = ensureDrawings('AAPL');
    upsertDrawing('AAPL', line('drawn-while-loading'));

    resolveGet({ ok: true, status: 200, json: async () => ({ drawings: [] }) });
    await pending;

    expect(getDrawings('AAPL').map((d) => d.id)).toEqual(['drawn-while-loading']);
  });

  it('a GET returning the list we already hold does not churn subscribers', async () => {
    fetchMock.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ drawings: [line('a')] }),
    }));
    await ensureDrawings('AAPL');

    const pane = vi.fn();
    subscribeDrawings('AAPL', pane);
    await ensureDrawings('AAPL');

    // No content change -- no rebuild, so a held selection survives a refetch.
    expect(pane).not.toHaveBeenCalled();
  });

  it('a failed PUT reports loudly rather than silently dropping the level', async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      (init?.method === 'PUT'
        ? { ok: false, status: 500, json: async () => ({}) }
        : { ok: true, status: 200, json: async () => ({ drawings: [] }) }),
    );
    upsertDrawing('AAPL', line('a'));
    await vi.advanceTimersByTimeAsync(CHART_DRAWINGS_SAVE_DEBOUNCE_MS + 10);
    expect(console.error).toHaveBeenCalled();
  });
});
