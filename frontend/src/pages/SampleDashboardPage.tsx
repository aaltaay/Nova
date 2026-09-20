/**
 * Sample-data dashboard — fixtures only. Never mounts useScannerData / HOD WS / watchlist API.
 * Scanner chrome lives on GlobalAppBar (SampleShell); HOD dock is middle-column only.
 */
import { useEffect, useState } from 'react';
import { ScannerSideNav } from '../components/TabNav';
import { TabModuleHost } from '../components/TabModuleHost';
import { SelectedScannerWidget } from '../components/SelectedScannerWidget';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { useExchangeFilter } from '../hooks/useExchangeFilter';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { ScannerDesk } from '../scanner/ScannerDesk';
import { useSampleData } from '../sample_data/SampleDataContext';
import { DISCOVERY_PROVIDER_DEFAULT } from '../constants';
import { setAccountNavActive } from '../components/accountNavActive';
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { SAMPLE_VOLUME_BOOST_ROWS } from '../volume_boost/sampleRows';
import { getModule, isTabModuleId, type ActiveTab } from '../workspace/registry';
import { isDockTab } from '../workspace/scannerTabs';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';

type Props = {
  onOpenTrader: (symbol: string) => void;
};

// The sample marking strip is owned by SampleShell (#357) so both sample
// branches carry it; this page must not render a second one.
export function SampleDashboardPage({ onOpenTrader }: Props) {
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
  const filteredLargeCap = exchangeFilter.filterRows(sample.largeCap);

  usePublishScannerNews({
    source: 'sample',
    gappers: sample.gappers,
    gainers: sample.gainers,
    losers: sample.losers,
    afterhours: sample.afterhours,
    catalysts: sample.catalysts,
  });

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

  useEffect(() => {
    setAccountNavActive(mainTab === 'trading' || mainTab === 'reports');
    return () => setAccountNavActive(false);
  }, [mainTab]);

  const navCounts = {
    gappers: filteredGappers.length,
    gainers: filteredGainers.length,
    losers: filteredLosers.length,
    afterhours: filteredAfterhours.length,
    largeCap: filteredLargeCap.length,
    catalysts: sample.catalysts.length,
    hodMomo: hodCount,
    runningUp: runningUpCount,
    watchlist: sample.watchlist.length,
    volumeBoost: SAMPLE_VOLUME_BOOST_ROWS.length,
  };

  return (
    <div className="nova-shell" data-testid="sample-dashboard">
      <ScannerSideNav
        activeTab={mainTab}
        railHighlight={railHighlight}
        onTabClick={handleTabClick}
        counts={navCounts}
        visibility={visibility}
      />

      <div className="main-col main-col--scanner-stack">
        <HodMomoDock onOpenTrading={onOpenTrader} />

        <ScannerDesk onOpenTrading={onOpenTrader}>
        <SelectedScannerWidget title={getModule(mainTab)?.title ?? 'Scanner'}>
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
              largeCap={filteredLargeCap}
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
              sampleMode
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
        watchlistEntries={sample.watchlist}
        widthPx={sidePanel.widthPx}
      />
    </div>
  );
}
