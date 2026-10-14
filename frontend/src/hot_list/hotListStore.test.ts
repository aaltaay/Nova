import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HOT_LIST_POLL_MS } from './constants';
import { getHotListState, hotListActions, resetHotListForTests, subscribeHotList } from './hotListStore';
import type { HotEntry, HotListView } from './types';

const api = vi.hoisted(() => ({
  fetchHotList: vi.fn(), starSymbol: vi.fn(), unstarSymbol: vi.fn(),
  patchHotList: vi.fn(), bringBackYesterday: vi.fn(),
}));
vi.mock('./hotListApi', () => api);

function view(): HotListView {
  return {
    schema_version: 1, date: '2026-10-14', cap: 20, auto_cap: 20,
    auto: { n: 0, start: '07:00', end: '16:00', rule: 'Fixture rule', error: null },
    entries: [
      { symbol: 'FIXTURE', how: 'star', at: 100, board: null, rank: null,
        change_pct: null, followed: true, why_not_followed: null },
      { symbol: 'SECOND', how: 'auto', at: 101, board: 'gainers', rank: 1,
        change_pct: 0.5, followed: false, why_not_followed: 'No fixture line' },
    ],
    yesterday: ['YESTERDAY', 'PRIOR'], error: null,
  };
}

describe('shared hot-list snapshot stability (#797)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetHotListForTests();
    for (const mock of Object.values(api)) mock.mockReset();
    api.fetchHotList.mockImplementation(async () => view());
  });

  afterEach(() => {
    resetHotListForTests();
    vi.useRealTimers();
  });

  it('retains the complete state and visible view for identical fresh objects, without extra notifications', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeHotList(listener);
    await Promise.resolve();
    const original = getHotListState();
    expect(listener).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(HOT_LIST_POLL_MS * 3);
    expect(api.fetchHotList).toHaveBeenCalledTimes(4);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getHotListState()).toBe(original);
    expect(getHotListState().view).toBe(original.view);
    unsubscribe();
    await vi.advanceTimersByTimeAsync(HOT_LIST_POLL_MS * 2);
    expect(api.fetchHotList).toHaveBeenCalledTimes(4);
  });

  const changes: Array<[string, (next: HotListView) => void]> = [
    ['date', next => { next.date = '2026-10-15'; }],
    ['schema version', next => { next.schema_version = 2; }],
    ['star cap', next => { next.cap = 21; }],
    ['auto cap', next => { next.auto_cap = null; }],
    ['auto count', next => { next.auto.n = 5; }],
    ['auto start', next => { next.auto.start = '08:00'; }],
    ['auto end', next => { next.auto.end = '15:00'; }],
    ['auto rule', next => { next.auto.rule = 'New rule'; }],
    ['auto error', next => { next.auto.error = 'Feed unavailable'; }],
    ['list error', next => { next.error = 'List unavailable'; }],
    ['entries added', next => { next.entries.push({ ...next.entries[0], symbol: 'THIRD' }); }],
    ['entries removed', next => { next.entries.pop(); }],
    ['entry order', next => { next.entries.reverse(); }],
    ['yesterday order', next => { next.yesterday.reverse(); }],
    ['yesterday content', next => { next.yesterday[1] = 'OTHER'; }],
    ['yesterday length', next => { next.yesterday.pop(); }],
  ];
  const entryChanges: HotEntry = {
    symbol: 'CHANGED', how: 'auto', at: 102, board: 'market', rank: 2,
    change_pct: 0.7, followed: null, why_not_followed: 'Scanner unavailable',
  };
  for (const key of Object.keys(entryChanges) as Array<keyof HotEntry>) {
    changes.push([`entry ${key}`, next => { Object.assign(next.entries[0], { [key]: entryChanges[key] }); }]);
  }

  it.each(changes)('notifies when %s changes', async (_name, change) => {
    await hotListActions.refresh();
    const previous = getHotListState();
    const changed = view();
    change(changed);
    api.fetchHotList.mockResolvedValue(changed);
    const listener = vi.fn();
    const unsubscribe = subscribeHotList(listener);
    await Promise.resolve();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getHotListState().view).toEqual(changed);
    expect(getHotListState()).not.toBe(previous);
    unsubscribe();
  });

  it('keeps the last view on errors, suppresses repeated equal errors, and publishes recovery', async () => {
    await hotListActions.refresh();
    const previous = getHotListState().view;
    api.fetchHotList.mockRejectedValue(new Error('Fixture unavailable'));
    const listener = vi.fn();
    const unsubscribe = subscribeHotList(listener);
    await Promise.resolve();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getHotListState().view).toBe(previous);
    expect(getHotListState().error).toBe('Fixture unavailable');
    const failed = getHotListState();
    await hotListActions.refresh();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(getHotListState()).toBe(failed);
    api.fetchHotList.mockResolvedValue(view());
    await hotListActions.refresh();
    expect(listener).toHaveBeenCalledTimes(2);
    expect(getHotListState().view).toBe(previous);
    expect(getHotListState().error).toBeNull();
    unsubscribe();
  });

  it('publishes both write busy transitions even when the answer has the same visible data', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeHotList(listener);
    await Promise.resolve();
    const previous = getHotListState().view;
    let resolve!: (answer: HotListView) => void;
    api.starSymbol.mockReturnValue(new Promise<HotListView>(done => { resolve = done; }));
    const pending = hotListActions.star('FIXTURE');
    expect(getHotListState().busy).toBe(true);
    expect(listener).toHaveBeenCalledTimes(2);
    resolve(view());
    expect(await pending).toBeNull();
    expect(listener).toHaveBeenCalledTimes(3);
    expect(getHotListState().busy).toBe(false);
    expect(getHotListState().view).toBe(previous);
    unsubscribe();
  });

  it('returns a write refusal and clears busy while retaining the last visible view', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeHotList(listener);
    await Promise.resolve();
    const previous = getHotListState().view;
    api.unstarSymbol.mockRejectedValue(new Error('Fixture refusal'));
    expect(await hotListActions.unstar('FIXTURE')).toBe('Fixture refusal');
    expect(listener).toHaveBeenCalledTimes(3);
    expect(getHotListState()).toEqual({ view: previous, error: null, busy: false });
    expect(getHotListState().view).toBe(previous);
    unsubscribe();
  });
});
