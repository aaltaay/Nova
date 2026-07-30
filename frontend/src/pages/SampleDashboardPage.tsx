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
import { useSampleData } from '../sample_data/SampleDataContext';
import { DISCOVERY_PROVIDER_DEFAULT, SAMPLE_DATA_BANNER, SAMPLE_DATA_SWITCH_LABEL } from '../constants';
import { setAccountNavActive } from '../components/accountNavActive';
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { getModule, isTabModuleId, type ActiveTab } from '../workspace/registry';
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

  useEffect(() => {
    setAccountNavActive(mainTab === 'trading' || mainTab === 'reports');
    return () => setAccountNavActive(false);
  }, [mainTab]);

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
      <ScannerSideNav
        activeTab={mainTab}
        railHighlight={railHighlight}
        onTabClick={handleTabClick}
        counts={navCounts}
        visibility={visibility}
      />

      <div className="main-col main-col--scanner-stack">
        <div className="sample-data-banner" role="status" data-testid="sample-data-banner">
          <span>{SAMPLE_DATA_BANNER}</span>
          <button type="button" className="history-banner-btn" onClick={onLeaveSample}>
            Exit {SAMPLE_DATA_SWITCH_LABEL}
          </button>
        </div>

        <HodMomoDock onOpenTrading={onOpenTrader} />

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
        </SelectedScannerWidget>
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
