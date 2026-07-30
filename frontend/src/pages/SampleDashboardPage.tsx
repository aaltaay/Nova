/**
 * Sample-data dashboard — fixtures only. Never mounts useScannerData / HOD WS / watchlist API.
 * HOD dock is owned by SampleShell (HodMomoFixtureProvider + HodMomoDock).
 */
import { useState } from 'react';
import { ScannerSideNav } from '../components/TabNav';
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
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { isTabModuleId, type ActiveTab } from '../workspace/registry';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';

type Props = {
  onOpenTrader: (symbol: string) => void;
  onLeaveSample: () => void;
};

function isDockTab(tab: ActiveTab): tab is 'hod_momo' | 'running_up' {
  return tab === 'hod_momo' || tab === 'running_up';
}

export function SampleDashboardPage({ onOpenTrader, onLeaveSample }: Props) {
  const sample = useSampleData();
  const { selectedSymbol, setSelectedSymbol } = useWorkspace();
  const { hodCount, runningUpCount, focusDock } = useHodMomo();
  const [activeTab, setActiveTab] = useState<ActiveTab>('gappers');
  const [railHighlight, setRailHighlight] = useState<ActiveTab>('gappers');
  const { visibility } = useModuleVisibility();
  const exchangeFilter = useExchangeFilter();
  const sidePanel = useSidePanelWidth();

  const filteredGappers = exchangeFilter.filterRows(sample.gappers);
  const filteredGainers = exchangeFilter.filterRows(sample.gainers);
  const filteredLosers = exchangeFilter.filterRows(sample.losers);
  const filteredAfterhours = exchangeFilter.filterRows(sample.afterhours);

  function handleTabClick(tab: ActiveTab) {
    if (!isTabModuleId(tab)) return;
    if (isDockTab(tab)) {
      focusDock(tab);
      setRailHighlight(tab);
      return;
    }
    setActiveTab(tab);
    setRailHighlight(tab);
  }

  const mainTab = isDockTab(activeTab) ? 'gappers' : activeTab;

  const navCounts = {
    gappers: filteredGappers.length,
    gainers: filteredGainers.length,
    losers: filteredLosers.length,
    afterhours: filteredAfterhours.length,
    catalysts: sample.catalysts.length,
    hodMomo: hodCount,
    runningUp: runningUpCount,
    watchlist: sample.watchlist.length,
  };

  return (
    <div className="nova-shell" data-testid="sample-dashboard">
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
        showScannerSource
        discoveryProvider={DISCOVERY_PROVIDER_DEFAULT}
        sampleDataActive
        onSampleDataToggle={(on) => {
          if (!on) onLeaveSample();
        }}
        accountActive={mainTab === 'trading' || mainTab === 'reports'}
        onAccountClick={
          visibility.trading === false
            ? undefined
            : () => handleTabClick('trading')
        }
      />

      <ScannerSideNav
        activeTab={mainTab}
        railHighlight={railHighlight}
        onTabClick={handleTabClick}
        counts={navCounts}
        visibility={visibility}
      />

      <div className="main-col">
        <div className="sample-data-banner" role="status" data-testid="sample-data-banner">
          <span>{SAMPLE_DATA_BANNER}</span>
          <button type="button" className="history-banner-btn" onClick={onLeaveSample}>
            Exit {SAMPLE_DATA_SWITCH_LABEL}
          </button>
        </div>

        <main className="panel">
          <TabModuleHost
            activeTab={mainTab}
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
