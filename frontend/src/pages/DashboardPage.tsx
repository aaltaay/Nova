/**
 * Main dashboard shell — rail + middle stack + quote panel.
 * Scanner status chrome is merged into GlobalAppBar (one header row).
 * HOD stream/config live in HodMomoProvider (AppShell); dock UI is middle-column only.
 */
import { useEffect, useRef, useState } from 'react';
import { ScannerSideNav } from '../components/TabNav';
import { TabModuleHost } from '../components/TabModuleHost';
import { SelectedScannerWidget } from '../components/SelectedScannerWidget';
import { GatewayDisconnectedBanner } from '../ibkr/GatewayDisconnectedBanner';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { GLOBAL_BAR_OPEN_TRADING_TAB_EVENT } from '../constants';
import { setAccountNavActive } from '../components/accountNavActive';
import { consumeOpenTradingTabRequest } from '../components/openTradingTabNav';
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { ScannerBarBridge } from '../components/ScannerBarBridge';
import { setGlobalBarHistoryDate } from '../components/scannerBarStore';
import { useWatchlist } from '../strategy/useWatchlist';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { useLiveScannerFeed } from '../scanner/ScannerDataContext';
import { useSettings } from '../settings/SettingsContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  DEFAULT_ACTIVE_TAB,
  getModule,
  isTabModuleId,
  tabUsesScannerPricePatch,
  type ActiveTab,
} from '../workspace/registry';
import { useModuleVisibility } from '../workspace/useModuleVisibility';

function isDockTab(tab: ActiveTab): tab is 'hod_momo' | 'running_up' {
  return tab === 'hod_momo' || tab === 'running_up';
}

function isMainScannerTab(tab: ActiveTab): boolean {
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

export function DashboardPage() {
  const {
    selectedSymbol,
    openStockView,
    selectRowSymbol,
    setDiscoveryProvider: setWorkspaceDiscovery,
    setAlpacaFeed: setWorkspaceAlpacaFeed,
    ibkrConnected,
    ibkrTransportConnected,
    ibkrPortsDark,
    ibkrDisconnectHint,
    ibkrSecondFactorStale,
    ibkrGatewayMode,
  } = useWorkspace();
  const { hodCount, runningUpCount, focusDock } = useHodMomo();
  const [activeTab, setActiveTab] = useState<ActiveTab>(DEFAULT_ACTIVE_TAB);
  const [railHighlight, setRailHighlight] = useState<ActiveTab>(DEFAULT_ACTIVE_TAB);
  const [tabOverridden, setTabOverridden] = useState(false);
  const tabOverriddenRef = useRef(false);
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
    setActiveTab(prev => {
      // Preserve Gainers vs Losers (same movers feed); do not clobber an open scanner tab
      // when session mode flips (e.g. market → afterhours) until the user opts in.
      if (prev === 'gainers' || prev === 'losers' || prev === 'gappers' || prev === 'afterhours') {
        return prev;
      }
      if (scanner.mode === 'market') return 'gainers';
      if (scanner.mode === 'afterhours') return 'afterhours';
      return 'gappers';
    });
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
    if (tabUsesScannerPricePatch(tab)) scanner.setL1ActiveTab(tab);
  }

  // Global Working menu / GlobalAppBar Account → Account / Trading tab.
  useEffect(() => {
    const openTrading = () => {
      if (visibility.trading === false) return;
      handleTabClick('trading');
    };
    // Latch survives Trader → Scanner remount (event may have fired while unmounted).
    if (consumeOpenTradingTabRequest()) openTrading();
    const onOpenTrading = () => {
      consumeOpenTradingTabRequest();
      openTrading();
    };
    window.addEventListener(GLOBAL_BAR_OPEN_TRADING_TAB_EVENT, onOpenTrading);
    return () => {
      window.removeEventListener(GLOBAL_BAR_OPEN_TRADING_TAB_EVENT, onOpenTrading);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [visibility.trading]);

  useEffect(() => {
    setAccountNavActive(activeTab === 'trading' || activeTab === 'reports');
    return () => setAccountNavActive(false);
  }, [activeTab]);

  const mainTab = isMainScannerTab(activeTab) ? activeTab : DEFAULT_ACTIVE_TAB;
  const activeHiddenCount = hiddenByExchangeFilter[mainTab] ?? 0;

  const navCounts = {
    gappers: filteredGappers.length,
    gainers: filteredGainers.length,
    losers: filteredLosers.length,
    afterhours: filteredAfterhours.length,
    largeCap: filteredLargeCap.length,
    catalysts: scanner.catalysts.length,
    hodMomo: hodCount,
    runningUp: runningUpCount,
    watchlist: watchlist.entries.length,
  };

  return (
    <div className="nova-shell">
      <ScannerBarBridge activeTab={mainTab} scanner={scanner} />
      <ScannerSideNav
        activeTab={mainTab}
        railHighlight={railHighlight}
        onTabClick={handleTabClick}
        counts={navCounts}
        visibility={visibility}
      />

      <div className="main-col main-col--scanner-stack">
        <GatewayDisconnectedBanner
          discoveryProvider={settings.discoveryProvider}
          ibkrConnected={ibkrConnected}
          ibkrTransportConnected={ibkrTransportConnected}
          ibkrPortsDark={ibkrPortsDark}
          ibkrDisconnectHint={ibkrDisconnectHint}
          ibkrGatewayMode={ibkrGatewayMode}
          ibkrSecondFactorStale={ibkrSecondFactorStale}
        />

        <HodMomoDock />

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
            />
          </main>
        </SelectedScannerWidget>
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
