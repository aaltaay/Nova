/**
 * Hard-gated sample route shell — never mounts live DashboardPage / scanner hooks.
 * ?view=sample → dashboard fixtures; ?view=sample&symbol=X → Trader with sample ticker.
 */
import { useCallback, useEffect, useState } from 'react';
import { AppErrorBoundary } from '../components/AppErrorBoundary';
import { GlobalAppBar } from '../components/GlobalAppBar';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { HodMomoFixtureProvider } from '../hod_momo/HodMomoFixtureProvider';
import { StockViewPage } from '../pages/StockViewPage';
import { SampleDashboardPage } from '../pages/SampleDashboardPage';
import {
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';
import {
  leaveSampleTraderUrl,
  leaveSampleView,
  parseSampleSymbol,
  replaceSampleTraderUrl,
} from './sampleNav';
import { SampleDataProvider, useSampleData } from './SampleDataContext';
import { useWorkspace } from '../workspace/WorkspaceContext';

function SampleShellInner() {
  const sample = useSampleData();
  const { selectedSymbol, setSelectedSymbol } = useWorkspace();
  const [traderSymbol, setTraderSymbol] = useState<string | null>(() => parseSampleSymbol());

  useEffect(() => {
    const sync = () => setTraderSymbol(parseSampleSymbol());
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

  useEffect(() => {
    if (selectedSymbol) return;
    const seed =
      sample.watchlist[0]?.symbol
      ?? sample.gappers[0]?.symbol
      ?? null;
    if (seed) setSelectedSymbol(seed);
  }, [selectedSymbol, sample.watchlist, sample.gappers, setSelectedSymbol]);

  const openTrader = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    replaceSampleTraderUrl(sym);
    setTraderSymbol(sym);
  }, []);

  const backToSampleDash = useCallback(() => {
    leaveSampleTraderUrl();
    setTraderSymbol(null);
  }, []);

  const sampleScannerBar = {
    mode: 'market' as const,
    health: sample.health,
    activeFeed: DATA_FEED_DEFAULT,
    feedFellBack: false,
    secondsAgo: 1,
    pricesStale: false,
    ibkrConnected: true,
    ibkrMode: 'paper' as const,
    ibkrGatewayMode: 'paper' as const,
    historyDate: null,
    historyDates: [],
    onHistoryChange: () => {},
    onLookup: setSelectedSymbol,
    showScannerSource: true,
    discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
    sampleDataActive: true,
    onSampleDataToggle: (on: boolean) => {
      if (!on) leaveSampleView();
    },
  };

  if (traderSymbol) {
    return (
      <HodMomoFixtureProvider>
        <div className="nova-app-stack">
          <GlobalAppBar scanner={sampleScannerBar} />
          <div className="nova-app-branch">
            <AppErrorBoundary source="sample-trader">
              <div className="nova-shell nova-shell--ticker-detail">
                <div className="main-col main-col--full main-col--trader-stack">
                  <HodMomoDock onOpenTrading={openTrader} />
                  <main className="ticker-detail-main">
                    <StockViewPage
                      symbol={traderSymbol}
                      detached
                      onBack={backToSampleDash}
                      onSelectSymbol={openTrader}
                    />
                  </main>
                </div>
              </div>
            </AppErrorBoundary>
          </div>
        </div>
      </HodMomoFixtureProvider>
    );
  }

  return (
    <HodMomoFixtureProvider>
      <div className="nova-app-stack">
        <GlobalAppBar scanner={sampleScannerBar} />
        <div className="nova-app-branch">
          <AppErrorBoundary source="sample-dashboard">
            <SampleDashboardPage onOpenTrader={openTrader} onLeaveSample={leaveSampleView} />
          </AppErrorBoundary>
        </div>
      </div>
    </HodMomoFixtureProvider>
  );
}

export function SampleShell() {
  return (
    <SampleDataProvider>
      <SampleShellInner />
    </SampleDataProvider>
  );
}
