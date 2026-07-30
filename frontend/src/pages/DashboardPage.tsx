/**
 * Main dashboard shell — header, tabs, side panel.
 * Settings overlay is owned by SettingsProvider at AppShell.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { useHodMomoConfig } from '../hod_momo/useHodMomoConfig';
import { partitionScannerAlerts } from '../hod_momo/scannerPartition';
import { collapseAlertsBySymbol } from '../hod_momo/collapseAlertsBySymbol';
import { ScannerSideNav } from '../components/TabNav';
import { TabModuleHost } from '../components/TabModuleHost';
import { AppHeader, fmtHistoryDate } from '../components/AppHeader';
import { GatewayDisconnectedBanner } from '../ibkr/GatewayDisconnectedBanner';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { GLOBAL_BAR_OPEN_TRADING_TAB_EVENT } from '../constants';
import { setAccountNavActive } from '../components/accountNavActive';
import { consumeOpenTradingTabRequest } from '../components/openTradingTabNav';
import { useWatchlist } from '../strategy/useWatchlist';
import { useScannerData } from '../hooks/useScannerData';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { useSettings } from '../settings/SettingsContext';
import { scanAgeForTab } from '../utils/scanAge';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  DEFAULT_ACTIVE_TAB,
  isTabModuleId,
  tabUsesScannerPricePatch,
  type ActiveTab,
} from '../workspace/registry';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { enterSampleView } from '../sample_data/sampleNav';

export function DashboardPage() {
  const {
    selectedSymbol,
    setSelectedSymbol,
    openStockView,
    setDiscoveryProvider: setWorkspaceDiscovery,
    setAlpacaFeed: setWorkspaceAlpacaFeed,
    scannerPersistentAuthoritative,
    ibkrConnected,
    ibkrMode,
    ibkrGatewayMode,
  } = useWorkspace();
  const [activeTab, setActiveTab] = useState<ActiveTab>(DEFAULT_ACTIVE_TAB);
  const [tabOverridden, setTabOverridden] = useState(false);
  const tabOverriddenRef = useRef(false);
  const [showHodSettings, setShowHodSettings] = useState(false);
  const { visibility } = useModuleVisibility();
  const { settings, exchangeFilter, registerOnConfigSaved } = useSettings();
  const sidePanel = useSidePanelWidth();
  const watchlist = useWatchlist(true);
  const hodMomoStream = useHodMomoStream();
  const hodMomoConfig = useHodMomoConfig();

  const fetchDataRef = useRef<() => void>(() => {});
  const scanner = useScannerData({
    discoveryProvider: settings.discoveryProvider,
    activeTab,
    scannerPersistentAuthoritative,
    onActiveFeed: settings.setActiveFeed,
    onFeedFellBack: settings.setFeedFellBack,
  });
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
    }
  }, [visibility, activeTab]);

  const showScannerPriceFreshness =
    tabUsesScannerPricePatch(activeTab) &&
    settings.discoveryProvider === 'ibkr' &&
    scanner.historyDate === null;
  const lastScan = scanAgeForTab(activeTab, scanner.scanAges);
  const priceAgeTs = scanner.lastPriceTs > 0 ? scanner.lastPriceTs : lastScan;
  const secondsAgo = showScannerPriceFreshness && priceAgeTs > 0
    ? Math.max(0, Math.floor(scanner.now - priceAgeTs))
    : null;

  function handleHistoryChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    if (val === '') {
      scanner.setHistoryDate(null);
      scanner.fetchData();
    } else {
      scanner.setHistoryDate(val);
    }
  }

  const filteredGappers = exchangeFilter.filterRows(scanner.gappers);
  const filteredGainers = exchangeFilter.filterRows(scanner.gainers);
  const filteredLosers = exchangeFilter.filterRows(scanner.losers);
  const filteredAfterhours = exchangeFilter.filterRows(scanner.afterhours);
  // Stable references so the 1Hz `scanner.now` clock tick (used only for
  // scanner-table staleness elsewhere on this page) does not force a fresh
  // partition + re-render of the HOD Momo tree on every render of this page.
  const { hodMomentum, runningUp } = useMemo(
    () => partitionScannerAlerts(hodMomoStream.alerts),
    [hodMomoStream.alerts],
  );
  const collapsedHodMomentum = useMemo(
    () => collapseAlertsBySymbol(hodMomentum),
    [hodMomentum],
  );
  const collapsedRunningUp = useMemo(
    () => collapseAlertsBySymbol(runningUp),
    [runningUp],
  );

  function handleTabClick(tab: ActiveTab) {
    if (!isTabModuleId(tab)) return;
    tabOverriddenRef.current = true;
    setTabOverridden(true);
    setActiveTab(tab);
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

  const navCounts = {
    gappers: filteredGappers.length,
    gainers: filteredGainers.length,
    losers: filteredLosers.length,
    afterhours: filteredAfterhours.length,
    catalysts: scanner.catalysts.length,
    hodMomo: collapsedHodMomentum.length,
    runningUp: collapsedRunningUp.length,
    watchlist: watchlist.entries.length,
  };

  return (
    <div className="nova-shell">
      <AppHeader
        portalToTop
        mode={scanner.mode}
        health={scanner.health}
        activeFeed={settings.activeFeed}
        feedFellBack={settings.feedFellBack}
        secondsAgo={secondsAgo}
        pricesStale={showScannerPriceFreshness && scanner.pricesStale}
        ibkrConnected={ibkrConnected}
        ibkrMode={ibkrMode}
        ibkrGatewayMode={ibkrGatewayMode}
        historyDate={scanner.historyDate}
        historyDates={scanner.historyDates}
        onHistoryChange={handleHistoryChange}
        onLookup={setSelectedSymbol}
        showScannerSource={activeTab !== 'trading' && activeTab !== 'reports'}
        discoveryProvider={settings.discoveryProvider}
        onBackendStarted={() => {
          void scanner.fetchData();
        }}
        sampleDataActive={false}
        onSampleDataToggle={(on) => {
          if (on) enterSampleView();
        }}
      />

      <ScannerSideNav
        activeTab={activeTab}
        onTabClick={handleTabClick}
        counts={navCounts}
        visibility={visibility}
      />

      <div className="main-col">
        <GatewayDisconnectedBanner
          discoveryProvider={settings.discoveryProvider}
          ibkrConnected={ibkrConnected}
          ibkrGatewayMode={ibkrGatewayMode}
        />

        <main className="panel">
          {scanner.historyDate && (
            <div className="history-banner">
              <span>Viewing {fmtHistoryDate(scanner.historyDate)}</span>
              <button
                type="button"
                className="history-banner-btn"
                onClick={() => {
                  scanner.setHistoryDate(null);
                  scanner.fetchData();
                }}
              >
                Back to Live
              </button>
            </div>
          )}

          <TabModuleHost
            activeTab={activeTab}
            mode={scanner.mode}
            health={scanner.health}
            discoveryProvider={settings.discoveryProvider}
            gappers={filteredGappers}
            gainers={filteredGainers}
            losers={filteredLosers}
            afterhours={filteredAfterhours}
            catalysts={scanner.catalysts}
            watchlistEntries={watchlist.entries}
            watchlistLoading={watchlist.loading}
            watchlistError={watchlist.error}
            selectedSymbol={selectedSymbol}
            onSelect={setSelectedSymbol}
            onOpenTrading={openStockView}
            pricesStale={scanner.pricesStale}
            flashSymbols={scanner.flashSymbols}
            rowQuoteTs={scanner.rowQuoteTs}
            nowSec={scanner.now}
            tableMeta={scanner.tableMeta}
            hodMomoStream={hodMomoStream}
            hodMomoConfig={hodMomoConfig}
            showHodSettings={showHodSettings}
            onToggleHodSettings={() => setShowHodSettings(s => !s)}
            onCloseHodSettings={() => setShowHodSettings(false)}
          />
        </main>
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
