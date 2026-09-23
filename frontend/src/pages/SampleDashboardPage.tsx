/**
 * Sample-data dashboard — fixtures only. Never mounts useScannerData / HOD WS / watchlist API.
 * Scanner chrome lives on GlobalAppBar (SampleShell); HOD dock is middle-column only.
 * Navigation is the shell's nav rail: this page publishes its tab state to
 * navRailStore and answers the rail's tab requests.
 */
import { useEffect, useMemo, useState } from 'react';
import { TabModuleHost } from '../components/TabModuleHost';
import { SelectedScannerWidget } from '../components/SelectedScannerWidget';
import { SidePanel } from '../components/SidePanel';
import { PanelResizeHandle } from '../components/PanelResizeHandle';
import { NAV_RAIL_SELECT_TAB_EVENT } from '../constantGroups/nav_rail';
import { useExchangeFilter } from '../hooks/useExchangeFilter';
import { useQuotePanelCollapsed } from '../hooks/useQuotePanelCollapsed';
import { useSidePanelWidth } from '../hooks/useSidePanelWidth';
import { ScannerDesk } from '../scanner/ScannerDesk';
import { useSampleData } from '../sample_data/SampleDataContext';
import { DISCOVERY_PROVIDER_DEFAULT } from '../constants';
import { useHodMomo } from '../hod_momo/HodMomoContext';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { SAMPLE_VOLUME_BOOST_ROWS } from '../volume_boost/sampleRows';
import {
  clearScannerNavState,
  consumeScannerTabRequest,
  publishScannerNavState,
} from '../workspace/navRailStore';
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
  const quotePanel = useQuotePanelCollapsed();

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

  // Nav rail → tab. The latch covers a request made before this page mounted.
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

  const mainTab = isDockTab(activeTab) ? 'gappers' : activeTab;

  const navCounts = useMemo(
    () => ({
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
    }),
    [
      filteredGappers.length,
      filteredGainers.length,
      filteredLosers.length,
      filteredAfterhours.length,
      filteredLargeCap.length,
      sample.catalysts.length,
      hodCount,
      runningUpCount,
      sample.watchlist.length,
    ],
  );

  useEffect(() => {
    publishScannerNavState({ activeTab: mainTab, railHighlight, counts: navCounts });
  }, [mainTab, railHighlight, navCounts]);
  useEffect(() => () => clearScannerNavState(), []);

  return (
    <div className="nova-shell nova-shell--scanner" data-testid="sample-dashboard">
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
      {!quotePanel.collapsed && (
        <PanelResizeHandle
          onPointerDown={sidePanel.onHandlePointerDown}
          dragging={sidePanel.dragging}
        />
      )}
      <SidePanel
        watchlistEntries={sample.watchlist}
        widthPx={sidePanel.widthPx}
        collapsed={quotePanel.collapsed}
        onToggleCollapsed={quotePanel.toggle}
      />
    </div>
  );
}
