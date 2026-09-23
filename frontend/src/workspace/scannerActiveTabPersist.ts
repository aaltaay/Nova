/**
 * Persist the last user-picked main scanner tab (D-042 / #88).
 * HOD dock prefs stay on `nova.hodMomo.dock.*` -- this key never writes those.
 */
import { SCANNER_ACTIVE_TAB_STORAGE_KEY } from '../constants';
import { readPref, writePref } from '../utils/prefStore';
import { DEFAULT_ACTIVE_TAB, type ActiveTab } from './registry';
import { isDockTab } from './scannerTabs';

/** Price / catalyst tables the operator can pin. Not HOD dock, not Account. */
export const PERSISTED_SCANNER_TABS = [
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'volume_boost',
  'large_cap',
  'catalysts',
] as const;

export type PersistedScannerTab = (typeof PERSISTED_SCANNER_TABS)[number];

/** Session tables that stay put when mode flips before the operator picks. */
const SESSION_STICKY_TABS = new Set<string>([
  'gappers',
  'gainers',
  'losers',
  'afterhours',
]);

export function isPersistedScannerTab(tab: string): tab is PersistedScannerTab {
  return (PERSISTED_SCANNER_TABS as readonly string[]).includes(tab);
}

export function parsePersistedScannerTab(raw: unknown): PersistedScannerTab | null {
  return typeof raw === 'string' && isPersistedScannerTab(raw) ? raw : null;
}

export function readPersistedScannerTab(
  storage: Pick<Storage, 'getItem'> = localStorage,
): PersistedScannerTab | null {
  return readPref(
    SCANNER_ACTIVE_TAB_STORAGE_KEY,
    null,
    parsePersistedScannerTab,
    storage,
  );
}

export function writePersistedScannerTab(
  tab: ActiveTab,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  if (isDockTab(tab) || !isPersistedScannerTab(tab)) return;
  writePref(SCANNER_ACTIVE_TAB_STORAGE_KEY, tab, storage);
}

export type ScannerTabInit = {
  tab: ActiveTab;
  userPicked: boolean;
};

/** Restore a stored user pick; otherwise Gappers and let session auto-switch run. */
export function initialScannerTabState(
  storage: Pick<Storage, 'getItem'> = localStorage,
): ScannerTabInit {
  const stored = readPersistedScannerTab(storage);
  if (stored) return { tab: stored, userPicked: true };
  return { tab: DEFAULT_ACTIVE_TAB, userPicked: false };
}

export function sessionDefaultScannerTab(mode: string): ActiveTab {
  if (mode === 'market') return 'gainers';
  if (mode === 'afterhours') return 'afterhours';
  return 'gappers';
}

/**
 * Premkt / RTH / AH defaults win until the operator has picked a tab.
 * A restored persist is a pick -- do not overwrite Large Cap / Catalysts.
 */
export function applySessionAutoSwitch(
  current: ActiveTab,
  mode: string,
  userPicked: boolean,
): ActiveTab {
  if (userPicked) return current;
  if (SESSION_STICKY_TABS.has(current)) return current;
  return sessionDefaultScannerTab(mode);
}
