/**
 * AppShell scanner dock modes -- HOD alert siblings plus IBKR roster tables.
 */
export const SCANNER_DOCK_ALERT_MODES = ['hod_momo', 'running_up'] as const;
export const SCANNER_DOCK_ROSTER_MODES = [
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'catalysts',
] as const;

export type ScannerDockAlertMode = (typeof SCANNER_DOCK_ALERT_MODES)[number];
export type ScannerDockRosterMode = (typeof SCANNER_DOCK_ROSTER_MODES)[number];
export type HodDockMode = ScannerDockAlertMode | ScannerDockRosterMode;

export const SCANNER_DOCK_MODE_LABEL: Record<HodDockMode, string> = {
  hod_momo: 'HOD Momo',
  running_up: 'Running Up',
  gappers: 'Gappers',
  gainers: 'Gainers',
  losers: 'Losers',
  afterhours: 'AH',
  catalysts: 'Catalysts',
};

export const SCANNER_DOCK_MODE_TITLE: Record<HodDockMode, string> = {
  hod_momo: 'HOD Momentum alerts',
  running_up: 'Running Up alerts',
  gappers: 'Gappers',
  gainers: 'Gainers',
  losers: 'Losers',
  afterhours: 'After Hours',
  catalysts: 'News catalysts',
};

export const SCANNER_DOCK_MODE_TESTID: Record<HodDockMode, string> = {
  hod_momo: 'hod-momo-dock-mode-hod',
  running_up: 'hod-momo-dock-mode-ru',
  gappers: 'hod-momo-dock-mode-gappers',
  gainers: 'hod-momo-dock-mode-gainers',
  losers: 'hod-momo-dock-mode-losers',
  afterhours: 'hod-momo-dock-mode-afterhours',
  catalysts: 'hod-momo-dock-mode-catalysts',
};

export function isAlertDockMode(mode: string): mode is ScannerDockAlertMode {
  return (SCANNER_DOCK_ALERT_MODES as readonly string[]).includes(mode);
}

export function isRosterDockMode(mode: string): mode is ScannerDockRosterMode {
  return (SCANNER_DOCK_ROSTER_MODES as readonly string[]).includes(mode);
}

export function isHodDockMode(mode: string): mode is HodDockMode {
  return isAlertDockMode(mode) || isRosterDockMode(mode);
}
