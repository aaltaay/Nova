/** Export / import browser desk prefs (localStorage only). */

import { ORDER_TABLE_COLUMNS_STORAGE_KEY } from '../constantGroups/chart_api';
import { TAPE_MIN_SIZE_STORAGE_KEY } from '../constantGroups/features';
import { SCANNER_ACTIVE_TAB_STORAGE_KEY } from '../constantGroups/market_ui';

export const PREFS_BUNDLE_VERSION = 1;
export const PREFS_DOWNLOAD_NAME = 'nova-prefs.json';

export const PREFS_BUNDLE_KEYS = [
  'nova.hotkeys.profile.v1',
  'nova.hotkeys.menu-default-epoch',
  'nova.hotkeys.desk-ask-bid-epoch',
  'nova_workspace_layout_v1',
  'nova_module_visibility_v1',
  'nova_side_panel_width_v1',
  'nova.theme',
  'nova.trade.defaults.v1',
  'nova.tickerTrade.skipPlaceConfirm',
  'nova.stockView.sideWidthPx',
  'nova.stockView.mainOrdersSplitPct',
  'nova.stockView.depthOrderSplitPct.v3',
  'nova.stockView.chartRowSplitPct',
  'nova.stockView.openOrders.collapsed',
  'nova.stockView.openOrders.sampleHidden',
  'nova.stockView.dock.surface',
  'nova.stockView.ordersToday.filter',
  ORDER_TABLE_COLUMNS_STORAGE_KEY,
  'nova.ibkr.orderTable.sort.v1.working',
  'nova.ibkr.orderTable.sort.v1.closed',
  'nova_exchange_filter_v1',
  SCANNER_ACTIVE_TAB_STORAGE_KEY,
  'nova.chartGrid.show10Sec',
  'nova.hodMomo.strip.v1',
  'nova_os_attention_muted',
  TAPE_MIN_SIZE_STORAGE_KEY,
] as const;

export interface PrefsBundle {
  version: number;
  exported_at: string;
  prefs: Record<string, string>;
}

export function exportPrefsBundle(
  storage: Pick<Storage, 'getItem'> = localStorage,
): PrefsBundle {
  const prefs: Record<string, string> = {};
  for (const key of PREFS_BUNDLE_KEYS) {
    const value = storage.getItem(key);
    if (value != null) prefs[key] = value;
  }
  return {
    version: PREFS_BUNDLE_VERSION,
    exported_at: new Date().toISOString(),
    prefs,
  };
}

export function importPrefsBundle(
  bundle: PrefsBundle,
  storage: Pick<Storage, 'setItem'> = localStorage,
): number {
  if (!bundle || bundle.version !== PREFS_BUNDLE_VERSION || !bundle.prefs) {
    throw new Error('Not a Nova prefs bundle');
  }
  let written = 0;
  const allowed = new Set<string>(PREFS_BUNDLE_KEYS);
  for (const [key, value] of Object.entries(bundle.prefs)) {
    if (!allowed.has(key) || typeof value !== 'string') continue;
    storage.setItem(key, value);
    written += 1;
  }
  return written;
}

export function downloadPrefsBundle(bundle: PrefsBundle = exportPrefsBundle()): void {
  const blob = new Blob([JSON.stringify(bundle, null, 2)], {
    type: 'application/json;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = PREFS_DOWNLOAD_NAME;
  a.click();
  URL.revokeObjectURL(url);
}

export async function readPrefsBundleFile(file: File): Promise<PrefsBundle> {
  const text = await file.text();
  const parsed = JSON.parse(text) as PrefsBundle;
  if (!parsed || parsed.version !== PREFS_BUNDLE_VERSION || !parsed.prefs) {
    throw new Error('Not a Nova prefs bundle');
  }
  return parsed;
}
