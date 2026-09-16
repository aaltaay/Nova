/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { TRADE_DEFAULTS_STORAGE_KEY } from '../constantGroups/trade_defaults';
import {
  defaultTradeDefaultsPrefs,
  parseTradeDefaultsPrefs,
  readTradeDefaultsPrefs,
  writeTradeDefaultsPrefs,
} from './tradeDefaultsPrefs';

describe('tradeDefaultsPrefs', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns defaults when empty / corrupt', () => {
    expect(readTradeDefaultsPrefs()).toEqual(defaultTradeDefaultsPrefs());
    expect(defaultTradeDefaultsPrefs().tradingHours).toBe('extended');
    localStorage.setItem(TRADE_DEFAULTS_STORAGE_KEY, '{not-json');
    expect(readTradeDefaultsPrefs()).toEqual(defaultTradeDefaultsPrefs());
    expect(parseTradeDefaultsPrefs(null)).toEqual(defaultTradeDefaultsPrefs());
  });

  it('keeps a saved Regular Hours pref instead of the new default', () => {
    writeTradeDefaultsPrefs({
      ...defaultTradeDefaultsPrefs(),
      tradingHours: 'rth',
    });
    expect(readTradeDefaultsPrefs().tradingHours).toBe('rth');
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
    writeTradeDefaultsPrefs(next);
    expect(readTradeDefaultsPrefs()).toEqual(next);
  });

  it('clamps invalid quantity and forces tif DAY', () => {
    const parsed = parseTradeDefaultsPrefs({
      orderType: 'STP',
      quantity: -3,
      tradingHours: 'rth',
      tif: 'GTC',
      limitPriceSource: 'last',
      stopOffsetPct: 1,
    });
    expect(parsed.quantity).toBe(defaultTradeDefaultsPrefs().quantity);
    expect(parsed.tif).toBe('DAY');
    expect(parsed.orderType).toBe('STP');
  });
});
