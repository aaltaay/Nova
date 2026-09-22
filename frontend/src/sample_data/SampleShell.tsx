/**
 * Hard-gated sample route shell — never mounts live DashboardPage / scanner hooks.
 * ?view=sample → dashboard fixtures; ?view=sample&symbol=X → Trader with sample ticker.
 * Carries the nav rail like the live shell so the sample desk navigates the same way.
 */
import { useCallback, useEffect, useState } from 'react';
import { AppErrorBoundary } from '../components/AppErrorBoundary';
import { GlobalAppBar } from '../components/GlobalAppBar';
import { NavRail } from '../components/NavRail';
import { HodMomoFixtureProvider } from '../hod_momo/HodMomoFixtureProvider';
import { IbkrAccountProvider } from '../ibkr/IbkrAccountContext';
import { NavPageHost } from '../pages/NavPageHost';
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
import { SampleModeBadge } from './SampleModeBadge';
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

  const rail = (
    <NavRail
      traderActive={traderSymbol != null}
      onOpenTrader={openTrader}
      onLeaveTrader={backToSampleDash}
      settings={null}
    />
  );

  if (traderSymbol) {
    return (
      <div className="nova-app-stack nova-app-stack--rail">
        {rail}
        <div className="nova-app-main">
          <GlobalAppBar scanner={sampleScannerBar} />
          <SampleModeBadge onExit={leaveSampleView} />
          <div className="nova-app-branch">
            <AppErrorBoundary source="sample-trader">
              <div className="nova-shell nova-shell--ticker-detail">
                <div className="main-col main-col--full main-col--trader-stack">
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
      </div>
    );
  }

  return (
    <HodMomoFixtureProvider>
      <div className="nova-app-stack nova-app-stack--rail">
        {rail}
        <div className="nova-app-main">
          <GlobalAppBar scanner={sampleScannerBar} />
          <SampleModeBadge onExit={leaveSampleView} />
          <div className="nova-app-branch">
            <AppErrorBoundary source="sample-dashboard">
              <NavPageHost onOpenTrader={openTrader}>
                <SampleDashboardPage onOpenTrader={openTrader} />
              </NavPageHost>
            </AppErrorBoundary>
          </div>
        </div>
      </div>
    </HodMomoFixtureProvider>
  );
}

export function SampleShell() {
  // SampleDataProvider must wrap IbkrAccountProvider so the poller serves
  // SAMPLE_IBKR_ACCOUNT_STATE (no live /api/ibkr/*). GlobalAppBar requires
  // the account context on both sample and live shells.
  return (
    <SampleDataProvider>
      <IbkrAccountProvider>
        <SampleShellInner />
      </IbkrAccountProvider>
    </SampleDataProvider>
  );
}
