import { describe, expect, it } from 'vitest';
import {
  getModule,
  HostRenderedModule,
  listModules,
  listTabModules,
  NOVA_MODULES,
  isTabModuleId,
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
    expect(isTabModuleId('dashboard')).toBe(true);
    expect(isTabModuleId('watchlist')).toBe(true);
    expect(isTabModuleId('running_up')).toBe(true);
    expect(isTabModuleId('level2')).toBe(false);
    expect(isTabModuleId('strategy')).toBe(false);
    expect(isTabModuleId('movers')).toBe(false);
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
});
