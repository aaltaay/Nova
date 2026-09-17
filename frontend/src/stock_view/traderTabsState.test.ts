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
  parseTraderTabs,
  promoteLive,
  releaseOldestLive,
  renameTab,
  serializeTraderTabs,
} from './traderTabsState';

const MAX = 3;

describe('traderTabsState', () => {
  it('adds and focuses a new tab', () => {
    const r = addTab(EMPTY_TRADER_TABS, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['NUWE'], active: 'NUWE', live: ['NUWE'] });
  });

  it('focuses an existing tab without duplicating', () => {
    const base = { tabs: ['AAPL', 'NUWE'], active: 'AAPL', live: ['AAPL', 'NUWE'] };
    const r = addTab(base, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['AAPL', 'NUWE'], active: 'NUWE', live: ['AAPL', 'NUWE'] });
  });

  it('keeps A B C on the strip and never blocks a 4th name', () => {
    let state = EMPTY_TRADER_TABS;
    for (const sym of ['A', 'B', 'C']) {
      state = addTab(state, sym, MAX).state;
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
      state = addTab(state, sym, MAX).state;
    }
    expect(state.live).toEqual(['B', 'C', 'D']);
    state = activateTab(state, 'A', MAX);
    expect(state.active).toBe('A');
    expect(state.live).toEqual(['C', 'D', 'A']);
    expect(isTabLive(state, 'B')).toBe(false);
  });

  it('closes active tab and selects a neighbor', () => {
    const state = { tabs: ['A', 'B', 'C'], active: 'B', live: ['A', 'B', 'C'] };
    expect(closeTab(state, 'B')).toEqual({ tabs: ['A', 'C'], active: 'C', live: ['A', 'C'] });
    expect(closeTab(state, 'A')).toEqual({ tabs: ['B', 'C'], active: 'B', live: ['B', 'C'] });
  });

  it('closes last tab to empty', () => {
    expect(closeTab({ tabs: ['A'], active: 'A', live: ['A'] }, 'A')).toEqual(EMPTY_TRADER_TABS);
  });

  it('renames a tab in place and keeps it live', () => {
    const r = renameTab({ tabs: ['A', 'B'], active: 'A', live: ['A', 'B'] }, 'A', 'zz', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['ZZ', 'B'], active: 'ZZ', live: ['B', 'ZZ'] });
  });

  it('rename to existing focuses and drops source', () => {
    const r = renameTab({ tabs: ['A', 'B'], active: 'A', live: ['A', 'B'] }, 'A', 'B', MAX);
    expect(r.state).toEqual({ tabs: ['B'], active: 'B', live: ['B'] });
  });

  it('draft tab commit becomes a real live symbol', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS).state;
    expect(draft.tabs).toEqual([TRADER_DRAFT_SYMBOL]);
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, 'mvo', MAX);
    expect(r.state).toEqual({ tabs: ['MVO'], active: 'MVO', live: ['MVO'] });
  });

  it('empty draft commit closes the draft', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS).state;
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, '  ', MAX);
    expect(r.state).toEqual(EMPTY_TRADER_TABS);
  });

  it('addDraftTab is never blocked at three live names', () => {
    const full = { tabs: ['A', 'B', 'C'], active: 'C', live: ['A', 'B', 'C'] };
    const r = addDraftTab(full);
    expect(r.blocked).toBe(false);
    expect(r.state.tabs).toEqual(['A', 'B', 'C', TRADER_DRAFT_SYMBOL]);
    expect(r.state.active).toBe(TRADER_DRAFT_SYMBOL);
    expect(r.state.live).toEqual(['A', 'B', 'C']);
  });

  it('activateTab no-ops for unknown symbols', () => {
    const state = { tabs: ['A'], active: 'A', live: ['A'] };
    expect(activateTab(state, 'B', MAX)).toEqual(state);
  });

  it('serialize drops drafts; parse round-trips live', () => {
    const raw = serializeTraderTabs({
      tabs: ['AAPL', TRADER_DRAFT_SYMBOL, 'NUWE'],
      active: TRADER_DRAFT_SYMBOL,
      live: ['AAPL', 'NUWE'],
    });
    expect(parseTraderTabs(raw)).toEqual({
      tabs: ['AAPL', 'NUWE'],
      active: 'AAPL',
      live: ['AAPL', 'NUWE'],
    });
  });

  it('parse seeds live from tabs when the field is missing (legacy persist)', () => {
    expect(parseTraderTabs(JSON.stringify({ tabs: ['A', 'B'], active: 'B' }))).toEqual({
      tabs: ['A', 'B'],
      active: 'B',
      live: ['A', 'B'],
    });
  });

  it('hydrateWithSymbol adds or focuses without a strip cap', () => {
    const stored = { tabs: ['AAPL'], active: 'AAPL', live: ['AAPL'] };
    expect(hydrateWithSymbol(stored, 'nuwe', MAX).state).toEqual({
      tabs: ['AAPL', 'NUWE'],
      active: 'NUWE',
      live: ['AAPL', 'NUWE'],
    });
    expect(hydrateWithSymbol(stored, 'aapl', MAX).state.active).toBe('AAPL');
    const over = hydrateWithSymbol(
      { tabs: ['A', 'B', 'C'], active: 'C', live: ['A', 'B', 'C'] },
      'D',
      MAX,
    );
    expect(over.blocked).toBe(false);
    expect(over.state.tabs).toEqual(['A', 'B', 'C', 'D']);
    expect(over.state.live).toEqual(['B', 'C', 'D']);
  });

  it('releaseOldestLive frees a slot after a gray extract', () => {
    const state = { tabs: ['A', 'B', 'C'], active: 'C', live: ['A', 'B', 'C'] };
    expect(releaseOldestLive(state)).toEqual({
      tabs: ['A', 'B', 'C'],
      active: 'C',
      live: ['B', 'C'],
    });
  });

  it('capLive keeps the most recently focused slots', () => {
    const state = { tabs: ['A', 'B', 'C', 'D'], active: 'D', live: ['A', 'B', 'C', 'D'] };
    expect(capLive(state, MAX).live).toEqual(['B', 'C', 'D']);
  });

  it('promoteLive on an already-live tab only reorders recency', () => {
    const state = { tabs: ['A', 'B', 'C'], active: 'C', live: ['A', 'B', 'C'] };
    expect(promoteLive(state, 'A', MAX).live).toEqual(['B', 'C', 'A']);
  });
});
