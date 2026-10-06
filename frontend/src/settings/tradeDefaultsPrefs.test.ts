/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TRADE_DEFAULTS_STORAGE_KEY } from '../constantGroups/trade_defaults';
import {
  defaultTradeDefaultsPrefs,
  parseTradeDefaultsPrefs,
  readTradeDefaultsPrefs,
  writeTradeDefaultsPrefs,
} from './tradeDefaultsPrefs';

describe('tradeDefaultsPrefs', () => {
  afterEach(() => vi.restoreAllMocks());
  beforeEach(() => {
    localStorage.clear();
  });

  it('isolates all defaults and leaves other venues on DAY without legs', () => {
    writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 25, tif: 'GTC', protectiveLegs: true });
    expect(readTradeDefaultsPrefs('paper')).toMatchObject({ quantity: 25, tif: 'GTC', protectiveLegs: true });
    expect(readTradeDefaultsPrefs('live')).toEqual(defaultTradeDefaultsPrefs());
    expect(readTradeDefaultsPrefs('sim')).toEqual(defaultTradeDefaultsPrefs());
  });

  it('waits for a confirmed venue, then adopts legacy settings into that venue only', () => {
    const legacy = { ...defaultTradeDefaultsPrefs(), quantity: 37, tif: 'GTC', protectiveLegs: true };
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, JSON.stringify(legacy));
    expect(readTradeDefaultsPrefs(null)).toEqual(defaultTradeDefaultsPrefs());
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).not.toBeNull();
    expect(readTradeDefaultsPrefs('sim')).toEqual(legacy);
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBeNull();
    expect(readTradeDefaultsPrefs('live')).toEqual(defaultTradeDefaultsPrefs());
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
  });

  it('keeps existing destination settings when legacy migration runs', () => {
    writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 19 });
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, JSON.stringify({ ...defaultTradeDefaultsPrefs(), quantity: 88 }));
    expect(readTradeDefaultsPrefs('paper').quantity).toBe(19);
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBeNull();
    expect(readTradeDefaultsPrefs('live').quantity).toBe(100);
  });

  it('preserves failed migrations and binds retry to the original confirmed venue', () => {
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, JSON.stringify({ ...defaultTradeDefaultsPrefs(), quantity: 45 }));
    const original = Storage.prototype.setItem;
    const save = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (key, value) {
      if (key === 'nova.trade.defaults.v2.paper') throw new Error('quota');
      original.call(this, key, value);
    });
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).not.toBeNull();
    save.mockRestore();
    expect(readTradeDefaultsPrefs('live')).toEqual(defaultTradeDefaultsPrefs());
    expect(readTradeDefaultsPrefs('paper').quantity).toBe(45);
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBeNull();
  });

  it('does not adopt legacy settings elsewhere when cleanup fails', () => {
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, JSON.stringify({ ...defaultTradeDefaultsPrefs(), quantity: 45 }));
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readTradeDefaultsPrefs('paper').quantity).toBe(45);
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).not.toBeNull();
    expect(readTradeDefaultsPrefs('live')).toEqual(defaultTradeDefaultsPrefs());
  });

  it('refuses unknown versions and mismatching destination ownership without rewriting them', () => {
    const raw = JSON.stringify({ schema_version: 99, venue: 'paper', prefs: { quantity: 88 } });
    localStorage.setItem('nova.trade.defaults.v2.paper', raw);
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(localStorage.getItem('nova.trade.defaults.v2.paper')).toBe(raw);
    localStorage.setItem('nova.trade.defaults.v2.sim', JSON.stringify({ schema_version: 2, venue: 'live', prefs: { quantity: 88 } }));
    expect(readTradeDefaultsPrefs('sim')).toEqual(defaultTradeDefaultsPrefs());
  });

  it('cannot persist to an unknown venue', () => {
    expect(writeTradeDefaultsPrefs(null, { ...defaultTradeDefaultsPrefs(), tif: 'GTC' })).toBe(false);
    expect(localStorage.length).toBe(0);
  });

  it('keeps sample reads and edits off operator settings and their migration receipt', () => {
    const legacy = JSON.stringify({ ...defaultTradeDefaultsPrefs(), quantity: 45 });
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, legacy);
    history.replaceState(null, '', '/?view=sample');
    try {
      expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
      expect(writeTradeDefaultsPrefs('paper', { ...defaultTradeDefaultsPrefs(), quantity: 3 })).toBe(false);
      expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBe(legacy);
      expect(localStorage.getItem('nova.trade.defaults.migration.v1')).toBeNull();
      expect(localStorage.getItem('nova.trade.defaults.v2.paper')).toBeNull();
    } finally { history.replaceState(null, '', '/'); }
  });

  it('preserves the legacy copy if receipt persistence or destination readback fails', () => {
    const legacy = JSON.stringify({ ...defaultTradeDefaultsPrefs(), quantity: 45 });
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, legacy);
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBe(legacy);
    set.mockRestore();
    const get = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (key) {
      return key === 'nova.trade.defaults.v2.paper' ? null : get.call(this, key);
    });
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBe(legacy);
    expect(readTradeDefaultsPrefs('live')).toEqual(defaultTradeDefaultsPrefs());
  });

  it('returns defaults when empty / corrupt', () => {
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(defaultTradeDefaultsPrefs().tradingHours).toBe('extended');
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, '{not-json');
    expect(readTradeDefaultsPrefs('paper')).toEqual(defaultTradeDefaultsPrefs());
    expect(parseTradeDefaultsPrefs(null)).toEqual(defaultTradeDefaultsPrefs());
  });

  it('keeps a saved Regular Hours pref instead of the new default', () => {
    writeTradeDefaultsPrefs('paper', {
      ...defaultTradeDefaultsPrefs(),
      tradingHours: 'rth',
    });
    expect(readTradeDefaultsPrefs('paper').tradingHours).toBe('rth');
  });

  it('round-trips a valid prefs object', () => {
    const next = {
      ...defaultTradeDefaultsPrefs(),
      orderType: 'LMT' as const,
      quantity: 50,
      tradingHours: 'extended' as const,
      limitPriceSource: 'mid' as const,
      stopOffsetPct: 2.5,
    };
    writeTradeDefaultsPrefs('paper', next);
    expect(readTradeDefaultsPrefs('paper')).toEqual(next);
  });

  it('clamps invalid quantity and keeps a supported tif', () => {
    const parsed = parseTradeDefaultsPrefs({
      orderType: 'STP',
      quantity: -3,
      tradingHours: 'rth',
      tif: 'GTC',
      limitPriceSource: 'last',
      stopOffsetPct: 1,
    });
    expect(parsed.quantity).toBe(defaultTradeDefaultsPrefs().quantity);
    expect(parsed.tif).toBe('GTC');
    expect(parsed.orderType).toBe('STP');
  });

  it('falls back to DAY for a tif Nova does not place (#91)', () => {
    expect(parseTradeDefaultsPrefs({ tif: 'IOC' }).tif).toBe('DAY');
    expect(parseTradeDefaultsPrefs({ tif: 7 }).tif).toBe('DAY');
  });

  it('keeps protective legs off unless they are explicitly true (#91)', () => {
    expect(defaultTradeDefaultsPrefs().protectiveLegs).toBe(false);
    expect(parseTradeDefaultsPrefs({}).protectiveLegs).toBe(false);
    expect(parseTradeDefaultsPrefs({ protectiveLegs: 'yes' }).protectiveLegs).toBe(
      false,
    );
    expect(parseTradeDefaultsPrefs({ protectiveLegs: true }).protectiveLegs).toBe(
      true,
    );
  });

  it('rejects leg offsets that are not real percentages (#91)', () => {
    const fallback = defaultTradeDefaultsPrefs();
    const parsed = parseTradeDefaultsPrefs({
      protectiveLegs: true,
      takeProfitPct: 0,
      stopLossPct: 150,
    });
    expect(parsed.takeProfitPct).toBe(fallback.takeProfitPct);
    expect(parsed.stopLossPct).toBe(fallback.stopLossPct);
    expect(
      parseTradeDefaultsPrefs({ takeProfitPct: 3.5, stopLossPct: 1.25 }),
    ).toMatchObject({ takeProfitPct: 3.5, stopLossPct: 1.25 });
  });

  it('round-trips GTC and protective legs through localStorage (#91)', () => {
    writeTradeDefaultsPrefs('paper', {
      ...defaultTradeDefaultsPrefs(),
      tif: 'GTC',
      protectiveLegs: true,
      takeProfitPct: 4,
      stopLossPct: 2,
    });
    const read = readTradeDefaultsPrefs('paper');
    expect(read.tif).toBe('GTC');
    expect(read.protectiveLegs).toBe(true);
    expect(read.takeProfitPct).toBe(4);
    expect(read.stopLossPct).toBe(2);
  });
});
