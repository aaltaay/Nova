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
    || tab === 'large_cap'
    || tab === 'catalysts'
    || tab === 'watchlist'
    || tab === 'trading'
    || tab === 'reports'
  );
}
