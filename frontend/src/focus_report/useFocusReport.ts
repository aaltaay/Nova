/**
 * The app shell's half of the focus report (ADR 033): what this window shows --
 * the page, the scanner tab, the symbol and where that symbol came from -- read
 * from the workspace and the nav rail and handed to the reporter.
 */
import { useEffect } from 'react';
import { TRADER_DRAFT_SYMBOL } from '../stock_view/traderTabsState';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { useNavRailSnapshot, type NavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { setFocusView, type FocusView } from './focusReporter';

/** The legacy dashboard tabs the Account item lights for (NavRail's rule). */
const ACCOUNT_TABS = new Set(['trading', 'reports']);

export interface FocusViewParts {
  detached: boolean;
  traderUp: boolean;
  deskUp: boolean;
  navPage: NavPage;
  scannerTab: string;
  activeTraderSymbol: string | null;
  traderTabs: string[];
  selectedSymbol: string | null;
}

/** What this window shows, in the report's terms. */
export function focusViewOf(parts: FocusViewParts): FocusView {
  const tabs = parts.traderTabs.filter((t) => t && t !== TRADER_DRAFT_SYMBOL);
  const active =
    parts.activeTraderSymbol && parts.activeTraderSymbol !== TRADER_DRAFT_SYMBOL ? parts.activeTraderSymbol : null;
  if (parts.detached || parts.traderUp) {
    return { page: 'trader', tab: null, symbol: active, symbolSource: active ? 'trader_tab' : null, traderTabs: tabs };
  }
  if (parts.deskUp) {
    const symbol = active ?? parts.selectedSymbol;
    return {
      page: 'desk',
      tab: null,
      symbol,
      symbolSource: active ? 'trader_tab' : symbol ? 'desk_board' : null,
      traderTabs: tabs,
    };
  }
  if (parts.navPage === 'dashboard' && !ACCOUNT_TABS.has(parts.scannerTab)) {
    const symbol = parts.selectedSymbol;
    return { page: 'scanner', tab: parts.scannerTab, symbol, symbolSource: symbol ? 'scanner_row' : null, traderTabs: tabs };
  }
  const page = parts.navPage === 'dashboard' ? 'account' : parts.navPage;
  return { page, tab: null, symbol: null, symbolSource: null, traderTabs: tabs };
}

export function useFocusReport(sampleMode: boolean, traderUp: boolean, deskUp: boolean): void {
  const { traderTabs, activeTraderSymbol, selectedSymbol } = useWorkspace();
  const { page, scanner } = useNavRailSnapshot();
  const view = focusViewOf({
    detached: traderTabs.length > 0 && parseStockViewSymbol() != null,
    traderUp,
    deskUp,
    navPage: page,
    scannerTab: scanner.activeTab,
    activeTraderSymbol,
    traderTabs,
    selectedSymbol,
  });
  const tabsKey = view.traderTabs.join(',');
  useEffect(() => {
    if (sampleMode) return;
    setFocusView({ ...view, traderTabs: tabsKey ? tabsKey.split(',') : [] });
    // The view's fields are the dependencies; the object is rebuilt every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleMode, view.page, view.tab, view.symbol, view.symbolSource, tabsKey]);
}
