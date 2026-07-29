import { describe, expect, it } from 'vitest';
import {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  activateTab,
  addDraftTab,
  addTab,
  closeTab,
  hydrateWithSymbol,
  parseTraderTabs,
  renameTab,
  serializeTraderTabs,
} from './traderTabsState';

const MAX = 3;

describe('traderTabsState', () => {
  it('adds and focuses a new tab', () => {
    const r = addTab(EMPTY_TRADER_TABS, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['NUWE'], active: 'NUWE' });
  });

  it('focuses an existing tab without duplicating', () => {
    const base = { tabs: ['AAPL', 'NUWE'], active: 'AAPL' };
    const r = addTab(base, 'nuwe', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['AAPL', 'NUWE'], active: 'NUWE' });
  });

  it('blocks a 4th distinct tab', () => {
    const full = { tabs: ['A', 'B', 'C'], active: 'A' };
    const r = addTab(full, 'D', MAX);
    expect(r.blocked).toBe(true);
    expect(r.state).toEqual(full);
  });

  it('closes active tab and selects a neighbor', () => {
    const state = { tabs: ['A', 'B', 'C'], active: 'B' };
    expect(closeTab(state, 'B')).toEqual({ tabs: ['A', 'C'], active: 'C' });
    expect(closeTab(state, 'A')).toEqual({ tabs: ['B', 'C'], active: 'B' });
  });

  it('closes last tab to empty', () => {
    expect(closeTab({ tabs: ['A'], active: 'A' }, 'A')).toEqual(EMPTY_TRADER_TABS);
  });

  it('renames a tab in place', () => {
    const r = renameTab({ tabs: ['A', 'B'], active: 'A' }, 'A', 'zz', MAX);
    expect(r.blocked).toBe(false);
    expect(r.state).toEqual({ tabs: ['ZZ', 'B'], active: 'ZZ' });
  });

  it('rename to existing focuses and drops source', () => {
    const r = renameTab({ tabs: ['A', 'B'], active: 'A' }, 'A', 'B', MAX);
    expect(r.state).toEqual({ tabs: ['B'], active: 'B' });
  });

  it('draft tab commit becomes a real symbol', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS, MAX).state;
    expect(draft.tabs).toEqual([TRADER_DRAFT_SYMBOL]);
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, 'mvo', MAX);
    expect(r.state).toEqual({ tabs: ['MVO'], active: 'MVO' });
  });

  it('empty draft commit closes the draft', () => {
    const draft = addDraftTab(EMPTY_TRADER_TABS, MAX).state;
    const r = renameTab(draft, TRADER_DRAFT_SYMBOL, '  ', MAX);
    expect(r.state).toEqual(EMPTY_TRADER_TABS);
  });

  it('activateTab no-ops for unknown symbols', () => {
    const state = { tabs: ['A'], active: 'A' };
    expect(activateTab(state, 'B')).toEqual(state);
  });

  it('serialize drops drafts; parse round-trips', () => {
    const raw = serializeTraderTabs({
      tabs: ['AAPL', TRADER_DRAFT_SYMBOL, 'NUWE'],
      active: TRADER_DRAFT_SYMBOL,
    });
    expect(parseTraderTabs(raw)).toEqual({ tabs: ['AAPL', 'NUWE'], active: 'AAPL' });
  });

  it('hydrateWithSymbol adds or focuses', () => {
    const stored = { tabs: ['AAPL'], active: 'AAPL' };
    expect(hydrateWithSymbol(stored, 'nuwe', MAX).state).toEqual({
      tabs: ['AAPL', 'NUWE'],
      active: 'NUWE',
    });
    expect(hydrateWithSymbol(stored, 'aapl', MAX).state.active).toBe('AAPL');
    expect(hydrateWithSymbol(
      { tabs: ['A', 'B', 'C'], active: 'A' },
      'D',
      MAX,
    ).blocked).toBe(true);
  });
});
