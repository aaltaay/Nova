import { describe, expect, it } from 'vitest';
import { MODULE_VISIBILITY_STORAGE_KEY } from '../constants';
import {
  defaultModuleVisibility,
  isModuleVisible,
  loadModuleVisibility,
  parseModuleVisibility,
  saveModuleVisibility,
} from './moduleVisibility';
import { listModules } from './registry';

function memoryStorage(seed: Record<string, string> = {}) {
  const store = { ...seed };
  return {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    _store: store,
  };
}

describe('moduleVisibility (Phase 4)', () => {
  it('defaults every registered module to visible', () => {
    const d = defaultModuleVisibility();
    for (const m of listModules()) {
      expect(d[m.id]).toBe(true);
    }
  });

  it('parse merges known ids and ignores junk', () => {
    const parsed = parseModuleVisibility(
      JSON.stringify({ gappers: false, level2: false, nope: false, tape: 'yes' }),
    );
    expect(parsed.gappers).toBe(false);
    expect(parsed.level2).toBe(false);
    expect(parsed.tape).toBe(true);
    expect(parsed.nope).toBeUndefined();
  });

  it('parse recovers from invalid JSON', () => {
    const parsed = parseModuleVisibility('{not-json');
    expect(parsed.dashboard).toBe(true);
  });

  it('load/save round-trip through storage', () => {
    const storage = memoryStorage();
    const map = defaultModuleVisibility();
    map.gappers = false;
    map.news = false;
    saveModuleVisibility(map, storage);
    expect(storage._store[MODULE_VISIBILITY_STORAGE_KEY]).toBeTruthy();
    const loaded = loadModuleVisibility(storage);
    expect(loaded.gappers).toBe(false);
    expect(loaded.news).toBe(false);
    expect(loaded.gainers).toBe(true);
  });

  it('isModuleVisible treats missing as visible', () => {
    expect(isModuleVisible('gappers', { gappers: false })).toBe(false);
    expect(isModuleVisible('gappers', {})).toBe(true);
  });
});
