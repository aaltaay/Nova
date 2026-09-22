/**
 * Nav rail store -- the shell page, the mounted dashboard's scanner state,
 * and the "select this scanner tab" latch.
 *
 * The rail lives in the app shell while the scanner tab state lives in
 * DashboardPage / SampleDashboardPage, which unmount on Trader, Desk and
 * Records. So the dashboard publishes here (like ScannerBarBridge does for the
 * header) and the rail asks for a tab through a latch that survives a remount
 * -- the same shape as the old openTradingTabNav, generalised to any tab.
 */
import { useSyncExternalStore } from 'react';
import { NAV_RAIL_SELECT_TAB_EVENT } from '../constantGroups/nav_rail';
import {
  DEFAULT_ACTIVE_TAB,
  getModule,
  isTabModuleId,
  type ActiveTab,
  type ModuleCountKey,
} from './registry';

/** What the dashboard slot shows while Trader is not up. */
export type NavPage = 'dashboard' | 'desk' | 'records';

export type NavCounts = Partial<Record<ModuleCountKey, number>>;

export type ScannerNavState = {
  /** Main-column tab (never a dock tab). */
  activeTab: ActiveTab;
  /** Rail highlight -- a dock tab while the HOD dock is focused. */
  railHighlight: ActiveTab;
  /** The last Scanner list shown -- where the Scanner item returns to from Account / Bots. */
  lastListTab: ActiveTab;
  counts: NavCounts;
  /** True while a dashboard is mounted and publishing. */
  mounted: boolean;
};

type NavRailSnapshot = {
  page: NavPage;
  scanner: ScannerNavState;
};

const INITIAL_SCANNER: ScannerNavState = {
  activeTab: DEFAULT_ACTIVE_TAB,
  railHighlight: DEFAULT_ACTIVE_TAB,
  lastListTab: DEFAULT_ACTIVE_TAB,
  counts: {},
  mounted: false,
};

let snapshot: NavRailSnapshot = { page: 'dashboard', scanner: INITIAL_SCANNER };
let pendingTab: ActiveTab | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): NavRailSnapshot {
  return snapshot;
}

export function getNavRailSnapshot(): NavRailSnapshot {
  return snapshot;
}

export function getNavPage(): NavPage {
  return snapshot.page;
}

export function setNavPage(page: NavPage): void {
  if (snapshot.page === page) return;
  snapshot = { ...snapshot, page };
  emit();
}

/** Dashboard publishes when its tab, highlight or counts change. */
export function publishScannerNavState(
  next: Pick<ScannerNavState, 'activeTab' | 'railHighlight' | 'counts'>,
): void {
  const prev = snapshot.scanner;
  if (
    prev.mounted
    && prev.activeTab === next.activeTab
    && prev.railHighlight === next.railHighlight
    && prev.counts === next.counts
  ) {
    return;
  }
  const lastListTab = getModule(next.activeTab)?.navGroup ? next.activeTab : prev.lastListTab;
  snapshot = { ...snapshot, scanner: { ...next, lastListTab, mounted: true } };
  emit();
}

/** Dashboard unmount: keep the last tab + counts so the rail does not blank, mark unmounted. */
export function clearScannerNavState(): void {
  if (!snapshot.scanner.mounted) return;
  snapshot = { ...snapshot, scanner: { ...snapshot.scanner, mounted: false } };
  emit();
}

/**
 * Ask the dashboard to select `tab`. Always routes the shell to the dashboard
 * page; the request is latched until a dashboard consumes it, and the event
 * reaches one that is already mounted.
 */
export function requestScannerTab(tab: ActiveTab): void {
  if (!isTabModuleId(tab)) return;
  pendingTab = tab;
  setNavPage('dashboard');
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(NAV_RAIL_SELECT_TAB_EVENT, { detail: { tab } }));
}

/** One-shot: the pending tab, or null. Dashboards call this on mount and on the event. */
export function consumeScannerTabRequest(): ActiveTab | null {
  const tab = pendingTab;
  pendingTab = null;
  return tab;
}

export function peekScannerTabRequest(): ActiveTab | null {
  return pendingTab;
}

export function useNavRailSnapshot(): NavRailSnapshot {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export function useNavPage(): NavPage {
  return useNavRailSnapshot().page;
}

/** Test helper. */
export function resetNavRailStoreForTests(): void {
  snapshot = { page: 'dashboard', scanner: INITIAL_SCANNER };
  pendingTab = null;
  emit();
}
