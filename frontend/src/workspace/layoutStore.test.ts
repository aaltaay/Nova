import { describe, expect, it } from 'vitest';
import { LAYOUT_SCHEMA_VERSION, LAYOUT_STORAGE_KEY } from '../constants';
import {
  coalesceQuoteOrder,
  defaultLayout,
  defaultSidePanelOrder,
  defaultStockViewOrder,
  getSlotOrder,
  loadLayout,
  migrateLayout,
  moveModuleInSlot,
  parseLayout,
  reorderModulesInSlot,
  resetLayout,
  saveLayout,
} from './layoutStore';

function memoryStorage(seed: Record<string, string> = {}) {
  const store = { ...seed };
  return {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    _store: store,
  };
}

describe('layoutStore (Phase 5)', () => {
  it('defaultLayout has current schema version and both slots', () => {
    const d = defaultLayout();
    expect(d.version).toBe(LAYOUT_SCHEMA_VERSION);
    expect(d.slots.side_panel).toEqual(defaultSidePanelOrder());
    expect(d.slots.stock_view).toEqual(defaultStockViewOrder());
  });

  it('parse recovers from invalid JSON', () => {
    const parsed = parseLayout('{not-json');
    expect(parsed).toEqual(defaultLayout());
  });

  it('migrate salvages known module ids and fills missing', () => {
    const migrated = migrateLayout({
      version: 1,
      slots: {
        side_panel: ['news', 'quote', 'nope', 'news'],
        stock_view: ['level2'],
      },
    });
    expect(migrated.version).toBe(LAYOUT_SCHEMA_VERSION);
    expect(migrated.slots.side_panel[0]).toBe('news');
    expect(migrated.slots.side_panel[1]).toBe('quote');
    expect(migrated.slots.side_panel).toContain('charts');
    expect(migrated.slots.side_panel).toContain('level2');
    expect(migrated.slots.side_panel).not.toContain('nope');
    expect(migrated.slots.stock_view[0]).toBe('level2');
    expect(migrated.slots.stock_view).toContain('quote');
  });

  it('migrate resets unknown future schema versions', () => {
    const migrated = migrateLayout({
      version: 99,
      slots: { side_panel: ['news'], stock_view: ['news'] },
    });
    expect(migrated).toEqual(defaultLayout());
  });

  it('load/save round-trip through storage', () => {
    const storage = memoryStorage();
    const layout = defaultLayout();
    layout.slots.side_panel = moveModuleInSlot(layout, 'side_panel', 'news', 'up').slots
      .side_panel;
    saveLayout(layout, storage);
    expect(storage._store[LAYOUT_STORAGE_KEY]).toBeTruthy();
    const loaded = loadLayout(storage);
    expect(loaded.slots.side_panel).toEqual(layout.slots.side_panel);
    expect(loaded.version).toBe(LAYOUT_SCHEMA_VERSION);
  });

  it('resetLayout restores defaults', () => {
    const storage = memoryStorage();
    const custom = moveModuleInSlot(defaultLayout(), 'side_panel', 'quote', 'up');
    saveLayout(custom, storage);
    const reset = resetLayout(storage);
    expect(reset).toEqual(defaultLayout());
    expect(JSON.parse(storage._store[LAYOUT_STORAGE_KEY]!)).toEqual(defaultLayout());
  });

  it('moveModuleInSlot swaps neighbors and no-ops at edges', () => {
    const base = defaultLayout();
    const order = getSlotOrder(base, 'side_panel');
    const first = order[0]!;
    expect(moveModuleInSlot(base, 'side_panel', first, 'up')).toBe(base);

    const moved = moveModuleInSlot(base, 'side_panel', 'news', 'up');
    const idx = moved.slots.side_panel.indexOf('news');
    expect(idx).toBe(order.indexOf('news') - 1);
    expect(moved.slots.stock_view).toEqual(base.slots.stock_view);
  });

  it('reorderModulesInSlot moves active onto over and no-ops same id', () => {
    const base = defaultLayout();
    expect(reorderModulesInSlot(base, 'side_panel', 'news', 'news')).toBe(base);

    // Default: charts, level2, tape, news, quote — drag news onto charts
    const moved = reorderModulesInSlot(base, 'side_panel', 'news', 'charts');
    expect(moved.slots.side_panel[0]).toBe('news');
    expect(moved.slots.side_panel).toContain('charts');
    expect(moved.slots.stock_view).toEqual(base.slots.stock_view);
  });
});

describe('coalesceQuoteOrder', () => {
  it('collapses level2+tape into one depth_tape block', () => {
    expect(coalesceQuoteOrder(['charts', 'level2', 'tape', 'news', 'quote'])).toEqual([
      'charts',
      'depth_tape',
      'news',
      'quote',
    ]);
    expect(coalesceQuoteOrder(['tape', 'news', 'level2', 'quote'])).toEqual([
      'depth_tape',
      'news',
      'quote',
    ]);
  });
});
