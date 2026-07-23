/**
 * Main dashboard shell — header, settings, tabs, side panel.
 * Extracted from App.tsx (root stays layout + Stock View gate only).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { useHodMomoConfig } from '../hod_momo/useHodMomoConfig';
import { partitionScannerAlerts } from '../hod_momo/scannerPartition';
import { TabNav } from '../components/TabNav';
import { TabModuleHost } from '../components/TabModuleHost';
import { AppHeader, fmtHistoryDate } from '../components/AppHeader';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { SettingsWorkspace } from '../components/SettingsWorkspace';
import { useWatchlist } from '../strategy/useWatchlist';
import { useScannerData } from '../hooks/useScannerData';
import { useSettingsForm } from '../hooks/useSettingsForm';
import { useExchangeFilter } from '../hooks/useExchangeFilter';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { scanAgeForTab } from '../utils/scanAge';
import { useWorkspace } from '../workspace/WorkspaceContext';
import {
  DEFAULT_ACTIVE_TAB,
  isTabModuleId,
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
  const exchangeFilter = useExchangeFilter();
  const sidePanel = useSidePanelWidth();
  const watchlist = useWatchlist(true);
  const hodMomoStream = useHodMomoStream();
  const hodMomoConfig = useHodMomoConfig();

  const fetchDataRef = useRef<() => void>(() => {});
  const settings = useSettingsForm(() => fetchDataRef.current());
  const scanner = useScannerData({
    discoveryProvider: settings.discoveryProvider,
    activeTab,
    scannerPersistentAuthoritative,
    onActiveFeed: settings.setActiveFeed,
    onFeedFellBack: settings.setFeedFellBack,
  });
  fetchDataRef.current = scanner.fetchData;

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
      if (prev === 'dashboard') return prev;
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

  // If the active tab was hidden via Modules menu, fall back to Dashboard.
  useEffect(() => {
    if (visibility[activeTab] === false) {
      setActiveTab(DEFAULT_ACTIVE_TAB);
    }
  }, [visibility, activeTab]);

  const lastScan = scanAgeForTab(activeTab, scanner.scanAges);
  const priceAgeTs = scanner.lastPriceTs > 0 ? scanner.lastPriceTs : lastScan;
  const secondsAgo =
    priceAgeTs > 0 ? Math.max(0, Math.floor(scanner.now - priceAgeTs)) : null;

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

  function handleTabClick(tab: ActiveTab) {
    if (!isTabModuleId(tab)) return;
    tabOverriddenRef.current = true;
    setTabOverridden(true);
    setActiveTab(tab);
  }

  return (
    <div className="nova-shell">
      <div className="main-col">
        <AppHeader
          mode={scanner.mode}
          health={scanner.health}
          activeFeed={settings.activeFeed}
          feedFellBack={settings.feedFellBack}
          secondsAgo={secondsAgo}
          pricesStale={
            scanner.pricesStale &&
            settings.discoveryProvider === 'ibkr' &&
            scanner.historyDate === null
          }
          ibkrConnected={ibkrConnected}
          ibkrMode={ibkrMode}
          ibkrGatewayMode={ibkrGatewayMode}
          historyDate={scanner.historyDate}
          historyDates={scanner.historyDates}
          onHistoryChange={handleHistoryChange}
          onLookup={setSelectedSymbol}
          showSettings={settings.showSettings}
          onToggleSettings={() => settings.setShowSettings(s => !s)}
          showScannerSource={activeTab !== 'trading' && activeTab !== 'reports'}
          discoveryProvider={settings.discoveryProvider}
          onBackendStarted={() => {
            void scanner.fetchData();
          }}
          accountActive={activeTab === 'trading' || activeTab === 'reports'}
          onAccountClick={
            visibility.trading === false
              ? undefined
              : () => handleTabClick('trading')
          }
          sampleDataActive={false}
          onSampleDataToggle={(on) => {
            if (on) enterSampleView();
          }}
        />

        {settings.showSettings && (
          <SettingsWorkspace
            apiKey={settings.apiKey}
            onApiKeyChange={settings.setApiKey}
            apiSecret={settings.apiSecret}
            onApiSecretChange={settings.setApiSecret}
            apiKeySet={settings.apiKeySet}
            apiSecretSet={settings.apiSecretSet}
            baseUrl={settings.baseUrl}
            onBaseUrlChange={settings.setBaseUrl}
            dataFeed={settings.dataFeed}
            onDataFeedChange={settings.setDataFeed}
            dataFeedOptions={settings.dataFeedOptions}
            discoveryProvider={settings.discoveryProvider}
            onSubmit={settings.handleConfigUpdate}
            onCancel={() => settings.setShowSettings(false)}
          />
        )}

        <main className="panel">
          <TabNav
            activeTab={activeTab}
            onTabClick={handleTabClick}
            counts={{
              gappers: filteredGappers.length,
              gainers: filteredGainers.length,
              losers: filteredLosers.length,
              afterhours: filteredAfterhours.length,
              catalysts: scanner.catalysts.length,
              hodMomo: hodMomentum.length,
              runningUp: runningUp.length,
              watchlist: watchlist.entries.length,
            }}
            visibility={visibility}
          />

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
            settings={settings}
            filter={exchangeFilter}
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
