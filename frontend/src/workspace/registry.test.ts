import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ACTIVE_TAB,
  getModule,
  HostRenderedModule,
  listModules,
  listScannerNavGroups,
  listTabModules,
  NAV_GROUP_ORDER,
  NOVA_MODULES,
  isTabModuleId,
  tabUsesScannerPricePatch,
} from './registry';

describe('module registry (Phase 4)', () => {
  it('has unique module ids', () => {
    const ids = NOVA_MODULES.map(m => m.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('lookup returns the registered module', () => {
    const g = getModule('gappers');
    expect(g?.title).toBe('Gappers');
    expect(g?.feedDeps).toContain('scanner');
    expect(getModule('nope')).toBeUndefined();
  });

  it('registers gainers and losers as separate modules sharing scanner feed', () => {
    const gainers = getModule('gainers');
    const losers = getModule('losers');
    expect(gainers?.defaultPlacement).toBe('tab');
    expect(losers?.defaultPlacement).toBe('tab');
    expect(gainers?.feedDeps).toEqual(['scanner']);
    expect(losers?.feedDeps).toEqual(['scanner']);
    expect(gainers?.component).toBe(HostRenderedModule);
    expect(losers?.component).toBe(HostRenderedModule);
  });

  it('lists TabNav modules (Account + Reports live in the header, not the tab bar)', () => {
    const tabs = listTabModules();
    expect(tabs.every(t => t.defaultPlacement === 'tab')).toBe(true);
    expect(tabs.every(t => t.showInTabNav !== false)).toBe(true);
    expect(tabs.map(t => t.id)).not.toContain('trading');
    expect(tabs.map(t => t.id)).not.toContain('reports');
    expect(getModule('trading')?.title).toBe('Account');
    expect(getModule('trading')?.showInTabNav).toBe(false);
    expect(getModule('reports')?.showInTabNav).toBe(false);
  });

  it('groups the Scanner tree for the nav rail: Lists, Signals, Mine in the approved order', () => {
    expect(NAV_GROUP_ORDER).toEqual(['lists', 'signals', 'mine']);
    const groups = listScannerNavGroups();
    expect(groups.map(g => g.group)).toEqual(['lists', 'signals', 'mine']);
    expect(groups[0].modules.map(m => m.id)).toEqual([
      'gappers', 'gainers', 'losers', 'running_up', 'afterhours', 'large_cap',
    ]);
    expect(groups[1].modules.map(m => m.id)).toEqual([
      'volume_boost', 'hod_momo', 'catalysts', 'earnings', 'nova_news',
    ]);
    expect(groups[2].modules.map(m => m.id)).toEqual(['watchlist']);
    // Account, Reports and Strategy are rail items of their own, never Scanner children.
    for (const id of ['trading', 'reports', 'strategy'] as const) {
      expect(getModule(id)?.navGroup).toBeUndefined();
    }
    // Every grouped module is a visible tab module.
    const tabIds = new Set(listTabModules().map(t => t.id));
    for (const g of groups) for (const m of g.modules) expect(tabIds.has(m.id)).toBe(true);
  });

  it('registers panel modules with real components', () => {
    for (const id of ['level2', 'tape', 'news', 'quote', 'charts', 'closed_orders'] as const) {
      const m = getModule(id);
      expect(m, id).toBeDefined();
      expect(m!.component).not.toBe(HostRenderedModule);
      expect(m!.defaultPlacement).not.toBe('tab');
    }
  });

  it('registers Closed Orders as an isolated hideable module (WID-027)', () => {
    const m = getModule('closed_orders');
    expect(m?.title).toBe('Closed Orders');
    expect(m?.defaultVisible).not.toBe(false);
    expect(m?.feedDeps).toEqual(['none']);
  });

  it('isTabModuleId gates ActiveTab ids', () => {
    expect(isTabModuleId('gappers')).toBe(true);
    expect(isTabModuleId('watchlist')).toBe(true);
    expect(isTabModuleId('running_up')).toBe(true);
    expect(isTabModuleId('dashboard')).toBe(false);
    expect(isTabModuleId('level2')).toBe(false);
    expect(isTabModuleId('strategy')).toBe(true);
    expect(isTabModuleId('movers')).toBe(false);
  });

  it('defaults homepage to Gappers and omits Dashboard from TabNav', () => {
    expect(DEFAULT_ACTIVE_TAB).toBe('gappers');
    expect(listTabModules().map(t => t.id)).not.toContain('dashboard');
    expect(getModule('dashboard')).toBeUndefined();
  });

  it('registers Volume boost as a derived L1 tab with no scanner price patch', () => {
    const tab = getModule('volume_boost');
    expect(tab?.title).toBe('Volume boost');
    expect(tab?.defaultPlacement).toBe('tab');
    expect(tab?.feedDeps).toEqual(['none']);
    expect(tab?.countKey).toBe('volumeBoost');
    expect(listTabModules().map(t => t.id)).toContain('volume_boost');
    expect(tabUsesScannerPricePatch('volume_boost')).toBe(false);
  });

  it('registers Earnings as a calendar tab with no scanner feed dependency', () => {
    const earnings = getModule('earnings');
    expect(earnings?.title).toBe('Earnings');
    expect(earnings?.defaultPlacement).toBe('tab');
    expect(earnings?.feedDeps).toEqual(['none']);
    expect(earnings?.countKey).toBe('earnings');
    expect(listTabModules().map(t => t.id)).toContain('earnings');
    expect(tabUsesScannerPricePatch('earnings')).toBe(false);
  });

  it('registers Nova News as a headline desk, not a scanner price tab', () => {
    const news = getModule('nova_news');
    expect(news?.title).toBe('Nova News');
    expect(news?.defaultPlacement).toBe('tab');
    expect(news?.feedDeps).toEqual(['news']);
    expect(news?.countKey).toBe('novaNews');
    expect(listTabModules().map(t => t.id)).toContain('nova_news');
    expect(tabUsesScannerPricePatch('nova_news')).toBe(false);
  });

  it('registers Strategy as a left-rail settings tab, not a scanner feed', () => {
    const strategy = getModule('strategy');
    expect(strategy?.title).toBe('Strategy');
    expect(strategy?.defaultPlacement).toBe('tab');
    expect(strategy?.feedDeps).toEqual(['none']);
    expect(listTabModules().map(t => t.id)).toContain('strategy');
    expect(tabUsesScannerPricePatch('strategy')).toBe(false);
  });

  it('registers Running Up as a sibling tab of HOD Momo', () => {
    const hod = getModule('hod_momo');
    const ru = getModule('running_up');
    expect(hod?.title).toBe('HOD Momo');
    expect(ru?.title).toBe('Running Up');
    expect(ru?.feedDeps).toEqual(['hod_momo']);
    expect(ru?.countKey).toBe('runningUp');
    expect(listTabModules().map(t => t.id)).toContain('running_up');
  });

  it('listModules includes every catalog entry', () => {
    expect(listModules().length).toBe(NOVA_MODULES.length);
  });

  it('tabUsesScannerPricePatch matches scanner feedDeps only', () => {
    for (const id of ['gappers', 'gainers', 'losers', 'afterhours', 'catalysts'] as const) {
      expect(tabUsesScannerPricePatch(id)).toBe(true);
    }
    for (const id of ['hod_momo', 'running_up', 'watchlist', 'trading', 'nova_news', 'strategy', 'volume_boost'] as const) {
      expect(tabUsesScannerPricePatch(id)).toBe(false);
    }
  });
});
