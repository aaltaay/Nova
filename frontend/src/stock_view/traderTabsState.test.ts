import { describe, expect, it } from 'vitest';
import {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  activateTab,
  addDraftTab,
  addTab,
  capLive,
  closeTab,
  hydrateWithSymbol,
  isTabLive,
  isTabPinned,
  parseTraderTabs,
  pinTab,
  previewTabOf,
  promoteLive,
  releaseOldestLive,
  renameTab,
  serializeTraderTabs,
  unpinTab,
} from './traderTabsState';

const MAX = 3;

/** A state written before preview tabs existed: no `pinned` field, read back as all pinned. */
function legacy(tabs: string[], active: string | null, live: string[]) {
  return { tabs, active, live } as unknown as Parameters<typeof addTab>[0];
}

/** Open a symbol by click and pin it, the way an operator keeps a tab. */
function openPinned(state: Parameters<typeof addTab>[0], sym: string) {
  return pinTab(addTab(state, sym, MAX).state, sym);
}

describe('traderTabsState', () => {
  it('adds and focuses a new tab as the preview (unpinned)', () => {
    const r = addTab(EMPTY_TRADER_TABS, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['NUWE'], active: 'NUWE', live: ['NUWE'], pinned: [] });
    expect(previewTabOf(r.state)).toBe('NUWE');
  });

  it('focuses an existing tab without duplicating', () => {
    const base = legacy(['AAPL', 'NUWE'], 'AAPL', ['AAPL', 'NUWE']);
    const r = addTab(base, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({
      tabs: ['AAPL', 'NUWE'], active: 'NUWE', live: ['AAPL', 'NUWE'], pinned: ['AAPL', 'NUWE'],
    });
  });

  it('a clicked ticker replaces the preview tab in place, keeping its live slot', () => {
    let state = openPinned(EMPTY_TRADER_TABS, 'A');
    state = addTab(state, 'B', MAX).state;
    expect(state.tabs).toEqual(['A', 'B']);
    expect(previewTabOf(state)).toBe('B');
    state = addTab(state, 'C', MAX).state;
    expect(state).toEqual({ tabs: ['A', 'C'], active: 'C', live: ['A', 'C'], pinned: ['A'] });
    state = addTab(state, 'D', MAX).state;
    expect(state.tabs).toEqual(['A', 'D']);
    expect(isTabPinned(state, 'A')).toBe(true);
    expect(isTabPinned(state, 'D')).toBe(false);
  });

  it('pinning keeps the tab, so the next ticker gets its own preview tab', () => {
    let state = addTab(EMPTY_TRADER_TABS, 'A', MAX).state;
    state = pinTab(state, 'A');
    state = addTab(state, 'B', MAX).state;
    expect(state.tabs).toEqual(['A', 'B']);
    expect(state.pinned).toEqual(['A']);
    state = pinTab(state, 'B');
    state = addTab(state, 'C', MAX).state;
    expect(state.tabs).toEqual(['A', 'B', 'C']);
    expect(state.pinned).toEqual(['A', 'B']);
  });

  it('unpinning makes a tab the preview again; the active unpinned tab is the one replaced', () => {
    let state = openPinned(openPinned(EMPTY_TRADER_TABS, 'A'), 'B');
    state = unpinTab(state, 'A');
    expect(previewTabOf(state)).toBe('A');
    state = activateTab(unpinTab(state, 'B'), 'B', MAX);
    expect(previewTabOf(state)).toBe('B');
    state = addTab(state, 'C', MAX).state;
    expect(state.tabs).toEqual(['A', 'C']);
  });

  it('pin and unpin ignore unknown symbols and drafts', () => {
    const state = addTab(EMPTY_TRADER_TABS, 'A', MAX).state;
    expect(pinTab(state, 'ZZZ')).toEqual(state);
    expect(pinTab(state, TRADER_DRAFT_SYMBOL)).toEqual(state);
    expect(unpinTab(state, 'A')).toEqual(state);
  });

  it('keeps A B C on the strip and never blocks a 4th name', () => {
    let state = EMPTY_TRADER_TABS;
    for (const sym of ['A', 'B', 'C']) {
      state = openPinned(state, sym);
    }
    expect(state.tabs).toEqual(['A', 'B', 'C']);
    expect(state.live).toEqual(['A', 'B', 'C']);
    const fourth = addTab(state, 'D', MAX);
    expect(fourth.blocked).toBe(false);
    expect(fourth.state.tabs).toEqual(['A', 'B', 'C', 'D']);
    expect(fourth.state.active).toBe('D');
    expect(fourth.state.live).toEqual(['B', 'C', 'D']);
    expect(isTabLive(fourth.state, 'A')).toBe(false);
    expect(isTabLive(fourth.state, 'D')).toBe(true);
  });

  it('promotes a gray tab and suspends the least-recent live tab', () => {
    let state = EMPTY_TRADER_TABS;
    for (const sym of ['A', 'B', 'C', 'D']) {
      state = openPinned(state, sym);
    }
    expect(state.live).toEqual(['B', 'C', 'D']);
    state = activateTab(state, 'A', MAX);
    expect(state.active).toBe('A');
    expect(state.live).toEqual(['C', 'D', 'A']);
    expect(isTabLive(state, 'B')).toBe(false);
  });

  it('closes active tab and selects a neighbor, dropping it from pinned', () => {
    const state = legacy(['A', 'B', 'C'], 'B', ['A', 'B', 'C']);
    expect(closeTab(state, 'B')).toEqual({ tabs: ['A', 'C'], active: 'C', live: ['A', 'C'], pinned: ['A', 'C'] });
    expect(closeTab(state, 'A')).toEqual({ tabs: ['B', 'C'], active: 'B', live: ['B', 'C'], pinned: ['B', 'C'] });
  });

  it('closes last tab to empty', () => {
    expect(closeTab(legacy(['A'], 'A', ['A']), 'A')).toEqual(EMPTY_TRADER_TABS);
  });

  it('renames a tab in place, keeps it live and pins the typed symbol', () => {
    const r = renameTab(legacy(['A', 'B'], 'A', ['A', 'B']), 'A', 'zz', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['ZZ', 'B'], active: 'ZZ', live: ['B', 'ZZ'], pinned: ['B', 'ZZ'] });
  });

  it('rename to existing focuses and drops source', () => {
    const r = renameTab(legacy(['A', 'B'], 'A', ['A', 'B']), 'A', 'B', MAX);
    expect(r.state).toEqual({ tabs: ['B'], active: 'B', live: ['B'], pinned: ['B'] });
  });

  it('draft tab commit becomes a real, pinned live symbol', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS).state;
    expect(draft.tabs).toEqual([TRADER_DRAFT_SYMBOL]);
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, 'mvo', MAX);
    expect(r.state).toEqual({ tabs: ['MVO'], active: 'MVO', live: ['MVO'], pinned: ['MVO'] });
  });

  it('empty draft commit closes the draft', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS).state;
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, '  ', MAX);
    expect(r.state).toEqual(EMPTY_TRADER_TABS);
  });

  it('addDraftTab is never blocked at three live names', () => {
    const full = legacy(['A', 'B', 'C'], 'C', ['A', 'B', 'C']);
    const r = addDraftTab(full);
    expect(r.blocked).toBe(false);
    expect(r.state.tabs).toEqual(['A', 'B', 'C', TRADER_DRAFT_SYMBOL]);
    expect(r.state.active).toBe(TRADER_DRAFT_SYMBOL);
    expect(r.state.live).toEqual(['A', 'B', 'C']);
    expect(r.state.pinned).toEqual(['A', 'B', 'C']);
  });

  it('activateTab no-ops for unknown symbols', () => {
    const state = legacy(['A'], 'A', ['A']);
    expect(activateTab(state, 'B', MAX)).toEqual({ ...state, pinned: ['A'] });
  });

  it('serialize drops drafts; parse round-trips live and pinned', () => {
    const raw = serializeTraderTabs({
      tabs: ['AAPL', TRADER_DRAFT_SYMBOL, 'NUWE'],
      active: TRADER_DRAFT_SYMBOL,
      live: ['AAPL', 'NUWE'],
      pinned: ['AAPL'],
    });
    expect(parseTraderTabs(raw)).toEqual({
      tabs: ['AAPL', 'NUWE'],
      active: 'AAPL',
      live: ['AAPL', 'NUWE'],
      pinned: ['AAPL'],
    });
  });

  it('parse seeds live from tabs and pins everything when the fields are missing (legacy persist)', () => {
    expect(parseTraderTabs(JSON.stringify({ tabs: ['A', 'B'], active: 'B' }))).toEqual({
      tabs: ['A', 'B'],
      active: 'B',
      live: ['A', 'B'],
      pinned: ['A', 'B'],
    });
  });

  it('hydrateWithSymbol adds or focuses without a strip cap', () => {
    const stored = legacy(['AAPL'], 'AAPL', ['AAPL']);
    expect(hydrateWithSymbol(stored, 'nuwe', MAX).state).toEqual({
      tabs: ['AAPL', 'NUWE'],
      active: 'NUWE',
      live: ['AAPL', 'NUWE'],
      pinned: ['AAPL'],
    });
    expect(hydrateWithSymbol(stored, 'aapl', MAX).state.active).toBe('AAPL');
    const over = hydrateWithSymbol(legacy(['A', 'B', 'C'], 'C', ['A', 'B', 'C']), 'D', MAX);
    expect(over.blocked).toBe(false);
    expect(over.state.tabs).toEqual(['A', 'B', 'C', 'D']);
    expect(over.state.live).toEqual(['B', 'C', 'D']);
  });

  it('releaseOldestLive frees a slot after a gray extract', () => {
    const state = legacy(['A', 'B', 'C'], 'C', ['A', 'B', 'C']);
    expect(releaseOldestLive(state)).toEqual({
      tabs: ['A', 'B', 'C'],
      active: 'C',
      live: ['B', 'C'],
      pinned: ['A', 'B', 'C'],
    });
  });

  it('capLive keeps the most recently focused slots', () => {
    const state = legacy(['A', 'B', 'C', 'D'], 'D', ['A', 'B', 'C', 'D']);
    expect(capLive(state, MAX).live).toEqual(['B', 'C', 'D']);
  });

  it('promoteLive on an already-live tab only reorders recency', () => {
    const state = legacy(['A', 'B', 'C'], 'C', ['A', 'B', 'C']);
    expect(promoteLive(state, 'A', MAX).live).toEqual(['B', 'C', 'A']);
  });
});
