/**
 * Main dashboard shell — header, settings, tabs, side panel.
 * Extracted from App.tsx (root stays layout + Stock View gate only).
 */
import { useEffect, useRef, useState } from 'react';
import { HodMomoTab } from '../hod_momo/HodMomoTab';
import { HodMomoSettings } from '../hod_momo/HodMomoSettings';
import { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { useHodMomoConfig } from '../hod_momo/useHodMomoConfig';
import { TabNav } from '../components/TabNav';
import type { ActiveTab } from '../components/TabNav';
import { AppHeader, fmtHistoryDate } from '../components/AppHeader';
import { SidePanel } from '../components/SidePanel';
import { SettingsPanel } from '../components/SettingsPanel';
import { ScannerTabPanels } from '../components/ScannerTabPanels';
import { DashboardTab } from './DashboardTab';
import { TradingTab } from '../ibkr/TradingTab';
import { WatchlistTab } from '../strategy/WatchlistTab';
import { useWatchlist } from '../strategy/useWatchlist';
import { ReportsTab } from '../reports/ReportsTab';
import { useScannerData } from '../hooks/useScannerData';
import { useSettingsForm } from '../hooks/useSettingsForm';
import { useExchangeFilter } from '../hooks/useExchangeFilter';
import { scanAgeForTab } from '../utils/scanAge';
import { API_BASE_URL } from '../constants';

interface Props {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
  onOpenTrading: (sym: string) => void;
}

export function DashboardPage({ selectedSymbol, setSelectedSymbol, onOpenTrading }: Props) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('dashboard');
  const [tabOverridden, setTabOverridden] = useState(false);
  const exchangeFilter = useExchangeFilter();
  const [showHodSettings, setShowHodSettings] = useState(false);
  const watchlist = useWatchlist(true);
  const hodMomoStream = useHodMomoStream();
  const hodMomoConfig = useHodMomoConfig();

  const fetchDataRef = useRef<() => void>(() => {});
  const settings = useSettingsForm(() => fetchDataRef.current());
  const scanner = useScannerData({
    discoveryProvider: settings.discoveryProvider,
    onActiveFeed: settings.setActiveFeed,
    onFeedFellBack: settings.setFeedFellBack,
  });
  fetchDataRef.current = scanner.fetchData;

  useEffect(() => {
    settings.fetchConfig();
  }, [settings.fetchConfig]);

  useEffect(() => {
    if (!tabOverridden) {
      // Keep user on Dashboard; mode-based tab switching only after they navigate away
      setActiveTab(prev => {
        if (prev !== 'dashboard') {
          if (scanner.mode === 'market') return 'movers';
          if (scanner.mode === 'afterhours') return 'afterhours';
          return 'gappers';
        }
        return prev;
      });
    }
  }, [scanner.mode, tabOverridden]);

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

  const scannerTab =
    activeTab === 'gappers' ||
    activeTab === 'movers' ||
    activeTab === 'afterhours' ||
    activeTab === 'catalysts';

  // Exchange-filtered arrays — applied to scanner tabs and Dashboard
  const filteredGappers = exchangeFilter.filterRows(scanner.gappers);
  const filteredGainers = exchangeFilter.filterRows(scanner.gainers);
  const filteredLosers  = exchangeFilter.filterRows(scanner.losers);
  const filteredAfterhours = exchangeFilter.filterRows(scanner.afterhours);

  return (
    <div className="container">
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
          historyDate={scanner.historyDate}
          historyDates={scanner.historyDates}
          onHistoryChange={handleHistoryChange}
          onLookup={setSelectedSymbol}
          showSettings={settings.showSettings}
          onToggleSettings={() => settings.setShowSettings(s => !s)}
          showScannerSource={activeTab !== 'trading'}
          discoveryProvider={settings.discoveryProvider}
        />

        {settings.showSettings && (
          <SettingsPanel
            apiKey={settings.apiKey}
            onApiKeyChange={settings.setApiKey}
            apiSecret={settings.apiSecret}
            onApiSecretChange={settings.setApiSecret}
            baseUrl={settings.baseUrl}
            onBaseUrlChange={settings.setBaseUrl}
            dataFeed={settings.dataFeed}
            onDataFeedChange={settings.setDataFeed}
            dataFeedOptions={settings.dataFeedOptions}
            discoveryProvider={settings.discoveryProvider}
            onDiscoveryProviderChange={settings.setDiscoveryProvider}
            discoveryProviderOptions={settings.discoveryProviderOptions}
            onSubmit={settings.handleConfigUpdate}
            onCancel={() => settings.setShowSettings(false)}
          />
        )}

        <main className="panel">
          <TabNav
            activeTab={activeTab}
            onTabClick={tab => {
              setActiveTab(tab);
              setTabOverridden(true);
            }}
            counts={{
              gappers: filteredGappers.length,
              movers: filteredGainers.length + filteredLosers.length,
              afterhours: filteredAfterhours.length,
              catalysts: scanner.catalysts.length,
              hodMomo: hodMomoStream.totalToday || hodMomoStream.alerts.length,
              watchlist: watchlist.entries.length,
            }}
          />

          {scanner.historyDate && (
            <div className="history-banner">
              <span>Viewing {fmtHistoryDate(scanner.historyDate)}</span>
              <button
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

          {activeTab === 'dashboard' && (
            <DashboardTab
              filter={exchangeFilter}
              apiKey={settings.apiKey}
              onApiKeyChange={settings.setApiKey}
              apiSecret={settings.apiSecret}
              onApiSecretChange={settings.setApiSecret}
              baseUrl={settings.baseUrl}
              onBaseUrlChange={settings.setBaseUrl}
              dataFeed={settings.dataFeed}
              onDataFeedChange={settings.setDataFeed}
              dataFeedOptions={settings.dataFeedOptions}
              discoveryProvider={settings.discoveryProvider}
              onDiscoveryProviderChange={settings.setDiscoveryProvider}
              discoveryProviderOptions={settings.discoveryProviderOptions}
              onSubmit={settings.handleConfigUpdate}
            />
          )}

          {scannerTab && (
            <ScannerTabPanels
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
              selectedSymbol={selectedSymbol}
              onSelect={setSelectedSymbol}
              onOpenTrading={onOpenTrading}
              pricesStale={scanner.pricesStale}
              flashSymbols={scanner.flashSymbols}
            />
          )}

          {activeTab === 'hod_momo' && (
            <>
              {showHodSettings && (
                <HodMomoSettings
                  config={hodMomoConfig}
                  onClose={() => setShowHodSettings(false)}
                />
              )}
              <HodMomoTab
                alerts={hodMomoStream.alerts}
                totalToday={hodMomoStream.totalToday}
                connected={hodMomoStream.connected}
                config={hodMomoConfig}
                selectedSymbol={selectedSymbol}
                onSelectSymbol={setSelectedSymbol}
                onOpenTrading={onOpenTrading}
                onOpenSettings={() => setShowHodSettings(s => !s)}
                onClearAlerts={() => {
                  if (!window.confirm(
                    'Clear all of today\'s HOD Momo alerts?\n\n'
                    + 'Past days in History are kept. New alerts will keep arriving.',
                  )) {
                    return;
                  }
                  fetch(`${API_BASE_URL}/api/hod-momo/alerts`, { method: 'DELETE' })
                    .catch(() => {});
                }}
              />
            </>
          )}
          {activeTab === 'trading' && <TradingTab />}
          {activeTab === 'strategy' && (
            <WatchlistTab
              entries={watchlist.entries}
              loading={watchlist.loading}
              error={watchlist.error}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={setSelectedSymbol}
              onOpenTrading={onOpenTrading}
            />
          )}
          {activeTab === 'reports' && <ReportsTab />}
        </main>
      </div>
      <SidePanel
        selectedSymbol={selectedSymbol}
        setSelectedSymbol={setSelectedSymbol}
        onOpenTrading={onOpenTrading}
        watchlistEntries={watchlist.entries}
        discoveryProvider={settings.discoveryProvider}
        alpacaFeed={settings.activeFeed}
      />
    </div>
  );
}
