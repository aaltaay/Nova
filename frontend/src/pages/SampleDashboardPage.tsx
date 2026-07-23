/**
 * Sample-data dashboard — fixtures only. Never mounts useScannerData / HOD WS / watchlist API.
 */
import { useMemo, useState } from 'react';
import { TabNav } from '../components/TabNav';
import { TabModuleHost } from '../components/TabModuleHost';
import { AppHeader } from '../components/AppHeader';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { useExchangeFilter } from '../hooks/useExchangeFilter';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { useSampleData } from '../sample_data/SampleDataContext';
import {
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
  SAMPLE_DATA_BANNER,
  SAMPLE_DATA_SWITCH_LABEL,
} from '../constants';
import { isTabModuleId, type ActiveTab } from '../workspace/registry';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import type { useHodMomoConfig } from '../hod_momo/useHodMomoConfig';
import type { useHodMomoStream } from '../hod_momo/useHodMomoStream';
import { partitionScannerAlerts } from '../hod_momo/scannerPartition';
import type { useSettingsForm } from '../hooks/useSettingsForm';

type Props = {
  onOpenTrader: (symbol: string) => void;
  onLeaveSample: () => void;
};

export function SampleDashboardPage({ onOpenTrader, onLeaveSample }: Props) {
  const sample = useSampleData();
  const [activeTab, setActiveTab] = useState<ActiveTab>('gappers');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(
    sample.watchlist[0]?.symbol ?? sample.gappers[0]?.symbol ?? null,
  );
  const [showHodSettings, setShowHodSettings] = useState(false);
  const { visibility } = useModuleVisibility();
  const exchangeFilter = useExchangeFilter();
  const sidePanel = useSidePanelWidth();

  const filteredGappers = exchangeFilter.filterRows(sample.gappers);
  const filteredGainers = exchangeFilter.filterRows(sample.gainers);
  const filteredLosers = exchangeFilter.filterRows(sample.losers);
  const filteredAfterhours = exchangeFilter.filterRows(sample.afterhours);
  const sampleScannerParts = useMemo(
    () => partitionScannerAlerts(sample.hodAlerts),
    [sample.hodAlerts],
  );

  const settings = useMemo(
    () =>
      ({
        showSettings: false,
        setShowSettings: () => {},
        apiKey: '',
        setApiKey: () => {},
        apiSecret: '',
        setApiSecret: () => {},
        apiKeySet: false,
        apiSecretSet: false,
        baseUrl: 'https://api.alpaca.markets',
        setBaseUrl: () => {},
        dataFeed: DATA_FEED_DEFAULT,
        setDataFeed: () => {},
        dataFeedOptions: ['iex', 'sip'],
        discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
        setDiscoveryProvider: () => {},
        discoveryProviderOptions: [DISCOVERY_PROVIDER_DEFAULT],
        activeFeed: DATA_FEED_DEFAULT,
        setActiveFeed: () => {},
        feedFellBack: false,
        setFeedFellBack: () => {},
        fetchConfig: async () => {},
        handleConfigUpdate: async (e: React.FormEvent) => {
          e.preventDefault();
        },
      }) as ReturnType<typeof useSettingsForm>,
    [],
  );

  const hodMomoStream = useMemo(
    () =>
      ({
        alerts: sample.hodAlerts,
        totalToday: sample.hodAlerts.length,
        connected: true,
      }) as ReturnType<typeof useHodMomoStream>,
    [sample.hodAlerts],
  );

  const hodMomoConfig = useMemo(
    () =>
      ({
        state: sample.hodConfig,
        updateStrategy: () => {},
        updateMaster: () => {},
        resetStrategy: async () => {},
        resetAll: async () => {},
      }) as ReturnType<typeof useHodMomoConfig>,
    [sample.hodConfig],
  );

  function handleTabClick(tab: ActiveTab) {
    if (!isTabModuleId(tab)) return;
    setActiveTab(tab);
  }

  return (
    <div className="nova-shell" data-testid="sample-dashboard">
      <div className="main-col">
        <AppHeader
          mode="market"
          health={sample.health}
          activeFeed={DATA_FEED_DEFAULT}
          feedFellBack={false}
          secondsAgo={1}
          pricesStale={false}
          ibkrConnected
          ibkrMode="paper"
          ibkrGatewayMode="paper"
          historyDate={null}
          historyDates={[]}
          onHistoryChange={() => {}}
          onLookup={setSelectedSymbol}
          showSettings={false}
          onToggleSettings={() => {}}
          showScannerSource
          discoveryProvider={DISCOVERY_PROVIDER_DEFAULT}
          sampleDataActive
          onSampleDataToggle={(on) => {
            if (!on) onLeaveSample();
          }}
          accountActive={activeTab === 'trading' || activeTab === 'reports'}
          onAccountClick={
            visibility.trading === false
              ? undefined
              : () => handleTabClick('trading')
          }
        />

        <div className="sample-data-banner" role="status" data-testid="sample-data-banner">
          <span>{SAMPLE_DATA_BANNER}</span>
          <button type="button" className="history-banner-btn" onClick={onLeaveSample}>
            Exit {SAMPLE_DATA_SWITCH_LABEL}
          </button>
        </div>

        <main className="panel">
          <TabNav
            activeTab={activeTab}
            onTabClick={handleTabClick}
            counts={{
              gappers: filteredGappers.length,
              gainers: filteredGainers.length,
              losers: filteredLosers.length,
              afterhours: filteredAfterhours.length,
              catalysts: sample.catalysts.length,
              hodMomo: sampleScannerParts.hodMomentum.length,
              runningUp: sampleScannerParts.runningUp.length,
              watchlist: sample.watchlist.length,
            }}
            visibility={visibility}
          />

          <TabModuleHost
            activeTab={activeTab}
            settings={settings}
            filter={exchangeFilter}
            mode="market"
            health={sample.health}
            discoveryProvider={DISCOVERY_PROVIDER_DEFAULT}
            gappers={filteredGappers}
            gainers={filteredGainers}
            losers={filteredLosers}
            afterhours={filteredAfterhours}
            catalysts={sample.catalysts}
            watchlistEntries={sample.watchlist}
            watchlistLoading={false}
            watchlistError={null}
            selectedSymbol={selectedSymbol}
            onSelect={setSelectedSymbol}
            onOpenTrading={onOpenTrader}
            pricesStale={false}
            flashSymbols={{}}
            rowQuoteTs={{}}
            nowSec={Date.now() / 1000}
            hodMomoStream={hodMomoStream}
            hodMomoConfig={hodMomoConfig}
            showHodSettings={showHodSettings}
            onToggleHodSettings={() => setShowHodSettings((s) => !s)}
            onCloseHodSettings={() => setShowHodSettings(false)}
          />
        </main>
      </div>
      <PanelResizeHandle
        onPointerDown={sidePanel.onHandlePointerDown}
        dragging={sidePanel.dragging}
      />
      <SidePanel
        watchlistEntries={sample.watchlist}
        widthPx={sidePanel.widthPx}
      />
    </div>
  );
}
