import { describe, expect, it } from 'vitest';
import { focusViewOf, type FocusViewParts } from './useFocusReport';

const BASE: FocusViewParts = {
  detached: false,
  traderUp: false,
  navPage: 'dashboard',
  scannerTab: 'gappers',
  activeTraderSymbol: 'GCTK',
  traderTabs: ['GCTK', 'PFSA', ''],
  selectedSymbol: 'VBIO',
};

describe('what a window shows', () => {
  it('Trader: the active tab, never the draft tab', () => {
    expect(focusViewOf({ ...BASE, traderUp: true })).toEqual({
      page: 'trader',
      tab: null,
      symbol: 'GCTK',
      symbolSource: 'trader_tab',
      traderTabs: ['GCTK', 'PFSA'],
    });
    expect(focusViewOf({ ...BASE, traderUp: true, activeTraderSymbol: '' }).symbol).toBeNull();
  });

  it('a pop-out is always the Trader', () => {
    expect(focusViewOf({ ...BASE, detached: true }).page).toBe('trader');
  });

  it('Market: the page, with no symbol of its own', () => {
    expect(focusViewOf({ ...BASE, navPage: 'market' })).toEqual({
      page: 'market',
      tab: null,
      symbol: null,
      symbolSource: null,
      traderTabs: ['GCTK', 'PFSA'],
    });
    // The Trader up wins over the page under it.
    expect(focusViewOf({ ...BASE, navPage: 'market', traderUp: true }).page).toBe('trader');
  });

  it('Scanner: the tab and the selected row', () => {
    expect(focusViewOf(BASE)).toMatchObject({ page: 'scanner', tab: 'gappers', symbol: 'VBIO', symbolSource: 'scanner_row' });
    expect(focusViewOf({ ...BASE, selectedSymbol: null })).toMatchObject({ symbol: null, symbolSource: null });
  });

  it('Account and Bots show no symbol', () => {
    expect(focusViewOf({ ...BASE, scannerTab: 'trading' })).toMatchObject({ page: 'account', symbol: null });
    expect(focusViewOf({ ...BASE, navPage: 'bots' })).toMatchObject({ page: 'bots', symbol: null });
    // Every page of the Bots group reads as the sensor's "bots" (2026-10-15).
    // LiveTrader Bots is the followed traders' page: it reads as it did as TraderTV LIVE (2026-10-15).
    expect(focusViewOf({ ...BASE, navPage: 'bots-live-trader' }).page).toBe('followed');
    expect(focusViewOf({ ...BASE, navPage: 'bots-strategy' }).page).toBe('bots');
    expect(focusViewOf({ ...BASE, navPage: 'records' }).page).toBe('records');
    expect(focusViewOf({ ...BASE, navPage: 'cryptos' }).page).toBe('cryptos');
  });
});
