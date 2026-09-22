/**
 * Main dashboard shell — middle stack + quote panel (the nav rail is the shell's).
 * Scanner status chrome is merged into GlobalAppBar (primary header row).
 * HOD stream/config live in HodMomoProvider (AppShell); dock UI is middle-column only.
 * Tab state is published to navRailStore; the rail's tab requests land here.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { TabModuleHost } from '../components/TabModuleHost';
import { SelectedScannerWidget } from '../components/SelectedScannerWidget';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { NAV_RAIL_SELECT_TAB_EVENT } from '../constantGroups/nav_rail';
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { ScannerBarBridge } from '../components/ScannerBarBridge';
import { setGlobalBarHistoryDate } from '../components/scannerBarStore';
import { useWatchlist } from '../strategy/useWatchlist';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { useLiveScannerFeed } from '../scanner/ScannerDataContext';
import { ScannerDesk } from '../scanner/ScannerDesk';
import { useSettings } from '../settings/SettingsContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  clearScannerNavState,
  consumeScannerTabRequest,
  publishScannerNavState,
} from '../workspace/navRailStore';
import {
  DEFAULT_ACTIVE_TAB,
  getModule,
  isTabModuleId,
  type ActiveTab,
} from '../workspace/registry';
import {
  applySessionAutoSwitch,
  initialScannerTabState,
  writePersistedScannerTab,
} from '../workspace/scannerActiveTabPersist';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { isDockTab, isMainScannerTab } from '../workspace/scannerTabs';

export function DashboardPage() {
  const {
    selectedSymbol,
    openStockView,
    selectRowSymbol,
    setDiscoveryProvider: setWorkspaceDiscovery,
    setAlpacaFeed: setWorkspaceAlpacaFeed,
  } = useWorkspace();
  const { hodCount, runningUpCount, focusDock } = useHodMomo();
  const persistedTab = initialScannerTabState();
  const [activeTab, setActiveTab] = useState<ActiveTab>(persistedTab.tab);
  const [railHighlight, setRailHighlight] = useState<ActiveTab>(persistedTab.tab);
  const [tabOverridden, setTabOverridden] = useState(persistedTab.userPicked);
  const tabOverriddenRef = useRef(persistedTab.userPicked);
  const { visibility } = useModuleVisibility();
  const { settings, exchangeFilter, registerOnConfigSaved } = useSettings();
  const sidePanel = useSidePanelWidth();
  const watchlist = useWatchlist(true);

  const fetchDataRef = useRef<() => void>(() => {});
  const scanner = useLiveScannerFeed();
  fetchDataRef.current = scanner.fetchData;

  useEffect(() => {
    registerOnConfigSaved(() => fetchDataRef.current());
  }, [registerOnConfigSaved]);

  useEffect(() => {
    settings.fetchConfig();
    // settings object identity changes every render; fetchConfig is the stable entry.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [settings.fetchConfig]);

  useEffect(() => {
    setWorkspaceDiscovery(settings.discoveryProvider);
  }, [settings.discoveryProvider, setWorkspaceDiscovery]);

  useEffect(() => {
    setWorkspaceAlpacaFeed(settings.activeFeed);
  }, [settings.activeFeed, setWorkspaceAlpacaFeed]);

  useEffect(() => {
    if (tabOverriddenRef.current) return;
    setActiveTab(prev => applySessionAutoSwitch(prev, scanner.mode, false));
  }, [scanner.mode, tabOverridden]);

  // If the active tab was hidden via Modules menu, fall back to Gappers.
  useEffect(() => {
    if (visibility[activeTab] === false) {
      setActiveTab(DEFAULT_ACTIVE_TAB);
      setRailHighlight(DEFAULT_ACTIVE_TAB);
    }
  }, [visibility, activeTab]);

  // Coerce any leftover HOD activeTab (pre-dock) into dock focus + Gappers main.
  useEffect(() => {
    if (!isDockTab(activeTab)) return;
    focusDock(activeTab);
    setRailHighlight(activeTab);
    setActiveTab(DEFAULT_ACTIVE_TAB);
  }, [activeTab, focusDock]);

  // Unfiltered rows: exchange filter must not hide HOD news flames.
  usePublishScannerNews({
    source: 'live',
    gappers: scanner.gappers,
    gainers: scanner.gainers,
    losers: scanner.losers,
    afterhours: scanner.afterhours,
    catalysts: scanner.catalysts,
    clear: scanner.historyDate !== null,
  });

  const filteredGappers = exchangeFilter.filterRows(scanner.gappers);
  const filteredGainers = exchangeFilter.filterRows(scanner.gainers);
  const filteredLosers = exchangeFilter.filterRows(scanner.losers);
  const filteredAfterhours = exchangeFilter.filterRows(scanner.afterhours);
  const filteredLargeCap = exchangeFilter.filterRows(scanner.largeCap);

  // Fail-loud (single-market-data-feed.mdc): a client-side filter must never
  // hide rows in silence. 2026-08-25 the exchange filter blanked the desk to
  // 1 row and nothing on screen said why.
  const hiddenByExchangeFilter: Record<string, number> = {
    gappers: scanner.gappers.length - filteredGappers.length,
    gainers: scanner.gainers.length - filteredGainers.length,
    losers: scanner.losers.length - filteredLosers.length,
    afterhours: scanner.afterhours.length - filteredAfterhours.length,
    large_cap: scanner.largeCap.length - filteredLargeCap.length,
  };

  function handleTabClick(tab: ActiveTab) {
    if (!isTabModuleId(tab)) return;
    if (isDockTab(tab)) {
      focusDock(tab);
      setRailHighlight(tab);
      return;
    }
    tabOverriddenRef.current = true;
    setTabOverridden(true);
    setActiveTab(tab);
    setRailHighlight(tab);
    writePersistedScannerTab(tab);
  }

  // Nav rail / Working menu / Settings → a tab. The latch survives the
  // Trader → Scanner remount (the request may have fired while unmounted).
  useEffect(() => {
    const apply = () => {
      const tab = consumeScannerTabRequest();
      if (!tab || visibility[tab] === false) return;
      handleTabClick(tab);
    };
    apply();
    window.addEventListener(NAV_RAIL_SELECT_TAB_EVENT, apply);
    return () => window.removeEventListener(NAV_RAIL_SELECT_TAB_EVENT, apply);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [visibility]);

  const mainTab = isMainScannerTab(activeTab) ? activeTab : DEFAULT_ACTIVE_TAB;
  const activeHiddenCount = hiddenByExchangeFilter[mainTab] ?? 0;

  // Declare the table actually on screen for IBKR L1, on mount as well as on
  // change. A click-only hint left `l1ActiveTab` at DEFAULT_ACTIVE_TAB after
  // every reload; Gappers freezes at 09:30, a frozen table contributes no
  // symbols (ADR 008), so OWNER_SCANNER subscribed nothing for a whole session
  // and half the visible Gainers rows never got a price. `tabHints` drops
  // non-scanner tabs, so passing Trading/Reports here correctly declares none.
  const setL1ActiveTab = scanner.setL1ActiveTab;
  useEffect(() => {
    setL1ActiveTab(mainTab);
  }, [mainTab, setL1ActiveTab]);

  const navCounts = useMemo(
    () => ({
      gappers: filteredGappers.length,
      gainers: filteredGainers.length,
      losers: filteredLosers.length,
      afterhours: filteredAfterhours.length,
      largeCap: filteredLargeCap.length,
      catalysts: scanner.catalysts.length,
      hodMomo: hodCount,
      runningUp: runningUpCount,
      watchlist: watchlist.entries.length,
    }),
    [
      filteredGappers.length,
      filteredGainers.length,
      filteredLosers.length,
      filteredAfterhours.length,
      filteredLargeCap.length,
      scanner.catalysts.length,
      hodCount,
      runningUpCount,
      watchlist.entries.length,
    ],
  );

  // The rail reads tab + highlight + counts from the store; it is not a child here.
  useEffect(() => {
    publishScannerNavState({ activeTab: mainTab, railHighlight, counts: navCounts });
  }, [mainTab, railHighlight, navCounts]);
  useEffect(() => () => clearScannerNavState(), []);

  return (
    <div className="nova-shell nova-shell--scanner">
      <ScannerBarBridge activeTab={mainTab} scanner={scanner} />

      <div className="main-col main-col--scanner-stack">
        <HodMomoDock />

        <ScannerDesk>
        <SelectedScannerWidget title={getModule(mainTab)?.title ?? 'Scanner'}>
          <main className="panel">
            {scanner.historyDate && (
              <div className="history-banner">
                <span>Viewing {scanner.historyDate}</span>
                <button
                  type="button"
                  className="history-banner-btn"
                  onClick={() => {
                    setGlobalBarHistoryDate(null);
                    scanner.setHistoryDate(null);
                    scanner.fetchData();
                  }}
                >
                  Back to Live
                </button>
              </div>
            )}

            {activeHiddenCount > 0 && (
              <div className="history-banner exchange-filter-banner">
                <span>
                  {activeHiddenCount} row{activeHiddenCount === 1 ? '' : 's'} hidden by
                  exchange filter -- open Settings &gt; General to adjust.
                </span>
              </div>
            )}

            <TabModuleHost
              activeTab={mainTab}
              mode={scanner.mode}
              health={scanner.health}
              discoveryProvider={settings.discoveryProvider}
              gappers={filteredGappers}
              gainers={filteredGainers}
              losers={filteredLosers}
              afterhours={filteredAfterhours}
              largeCap={filteredLargeCap}
              catalysts={scanner.catalysts}
              watchlistEntries={watchlist.entries}
              watchlistLoading={watchlist.loading}
              watchlistError={watchlist.error}
              selectedSymbol={selectedSymbol}
              onSelect={selectRowSymbol}
              onOpenTrading={openStockView}
              pricesStale={scanner.pricesStale}
              flashSymbols={scanner.flashSymbols}
              rowQuoteTs={scanner.rowQuoteTs}
              nowSec={scanner.now}
              tableMeta={scanner.tableMeta}
              historyDate={scanner.historyDate}
            />
          </main>
        </SelectedScannerWidget>
        </ScannerDesk>
      </div>
      <PanelResizeHandle
        onPointerDown={sidePanel.onHandlePointerDown}
        dragging={sidePanel.dragging}
      />
      <SidePanel
        watchlistEntries={watchlist.entries}
        widthPx={sidePanel.widthPx}
      />
    </div>
  );
}
