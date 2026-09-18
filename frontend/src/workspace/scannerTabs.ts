import type { ActiveTab } from './registry';

/** HOD Momo / Running Up are alert dock modes, not main scanner tables. */
export function isDockTab(tab: ActiveTab): tab is 'hod_momo' | 'running_up' {
  return tab === 'hod_momo' || tab === 'running_up';
}

/** Tabs the Dashboard renders in its main panel (scanner tables + account views). */
export function isMainScannerTab(tab: ActiveTab): boolean {
  return (
    tab === 'gappers'
    || tab === 'gainers'
    || tab === 'losers'
    || tab === 'afterhours'
    || tab === 'volume_boost'
    || tab === 'large_cap'
    || tab === 'earnings'
    || tab === 'nova_news'
    || tab === 'catalysts'
    || tab === 'watchlist'
    || tab === 'strategy'
    || tab === 'trading'
    || tab === 'reports'
  );
}

/** Volume boost watches existing L1 -- never declare it as the active table. */
export function declaresScannerL1(tab: ActiveTab): boolean {
  return tab !== 'volume_boost';
}
