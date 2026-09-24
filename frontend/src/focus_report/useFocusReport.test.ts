import { describe, expect, it } from 'vitest';
import { focusViewOf, type FocusViewParts } from './useFocusReport';

const BASE: FocusViewParts = {
  detached: false,
  traderUp: false,
  deskUp: false,
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

  it('Desk: the active Trader tab, else the board selection', () => {
    expect(focusViewOf({ ...BASE, deskUp: true })).toMatchObject({ page: 'desk', symbol: 'GCTK', symbolSource: 'trader_tab' });
    expect(focusViewOf({ ...BASE, deskUp: true, activeTraderSymbol: null })).toMatchObject({
      symbol: 'VBIO',
      symbolSource: 'desk_board',
    });
  });

  it('Scanner: the tab and the selected row', () => {
    expect(focusViewOf(BASE)).toMatchObject({ page: 'scanner', tab: 'gappers', symbol: 'VBIO', symbolSource: 'scanner_row' });
    expect(focusViewOf({ ...BASE, selectedSymbol: null })).toMatchObject({ symbol: null, symbolSource: null });
  });

  it('Account and Bots show no symbol', () => {
    expect(focusViewOf({ ...BASE, scannerTab: 'trading' })).toMatchObject({ page: 'account', symbol: null });
    expect(focusViewOf({ ...BASE, navPage: 'bots' })).toMatchObject({ page: 'bots', symbol: null });
    expect(focusViewOf({ ...BASE, navPage: 'records' }).page).toBe('records');
  });
});
