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
    writeTradeDefaultsPrefs({
      ...defaultTradeDefaultsPrefs(),
      tif: 'GTC',
      protectiveLegs: true,
      takeProfitPct: 4,
      stopLossPct: 2,
    });
    const read = readTradeDefaultsPrefs();
    expect(read.tif).toBe('GTC');
    expect(read.protectiveLegs).toBe(true);
    expect(read.takeProfitPct).toBe(4);
    expect(read.stopLossPct).toBe(2);
  });
});
