/**
 * @vitest-environment jsdom
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { TRADE_DEFAULTS_STORAGE_KEY } from '../constantGroups/trade_defaults';
import { applyTicketDefaults } from './applyTicketDefaults';
import { defaultTradeDefaultsPrefs, writeTradeDefaultsPrefs } from '../settings/tradeDefaultsPrefs';

describe('applyTicketDefaults extended hours', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('defaults Extended Hours on for Market when no prefs exist', () => {
    const next = applyTicketDefaults('AAPL', 25, null);
    expect(next.orderType).toBe('MKT');
    expect(next.outsideRth).toBe(true);
    expect(defaultTradeDefaultsPrefs().tradingHours).toBe('extended');
  });

  it('honors a saved Regular Hours pref on Market', () => {
    writeTradeDefaultsPrefs({
      ...defaultTradeDefaultsPrefs(),
      orderType: 'MKT',
      tradingHours: 'rth',
    });
    expect(applyTicketDefaults('MSFT', 10, null).outsideRth).toBe(false);
  });

  it('keeps Extended Hours on for Market when prefs say extended', () => {
    writeTradeDefaultsPrefs({
      ...defaultTradeDefaultsPrefs(),
      orderType: 'MKT',
      tradingHours: 'extended',
    });
    expect(applyTicketDefaults('NVDA', 100, null).outsideRth).toBe(true);
  });

  it('does not write prefs just by reading defaults', () => {
    applyTicketDefaults('AAPL', 25, null);
    expect(localStorage.getItem(TRADE_DEFAULTS_STORAGE_KEY)).toBeNull();
  });
});
