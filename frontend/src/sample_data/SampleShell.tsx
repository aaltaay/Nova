/**
 * Hard-gated sample route shell -- never mounts live DashboardPage / scanner hooks.
 * ?view=sample → dashboard fixtures; ?view=sample&symbol=X → the Trader on X;
 * ?view=sample&symbol=X&popout=1 → a sample Trader tab popped out.
 *
 * The sample desk has its own workspace (#449, SampleWorkspaceProvider): its
 * Trader tabs, Focus rail, Desk and pop-out live in memory and never touch the
 * operator's saved workspace. It is laid out like the live shell (App.tsx):
 * the nav rail and header, the Trader slot -- shown full, or beside the Desk
 * board -- and the dashboard slot. A pop-out has neither rail nor header.
 */
import { useEffect, useMemo, useState } from 'react';
import { AppErrorBoundary } from '../components/AppErrorBoundary';
import { GlobalAppBar } from '../components/GlobalAppBar';
import { NavRail } from '../components/NavRail';
import { BotSymbolMenuHost } from '../bot/BotSymbolMenu';
import { HodMomoFixtureProvider } from '../hod_momo/HodMomoFixtureProvider';
import { IbkrAccountProvider } from '../ibkr/IbkrAccountContext';
import { NavPageHost } from '../pages/NavPageHost';
import { SampleDashboardPage } from '../pages/SampleDashboardPage';
import { ScannerDataContextProvider } from '../scanner/ScannerDataContext';
import { FloatDeskChrome } from '../stock_view/FloatDeskChrome';
import { memoryFocusRailStore } from '../stock_view/focusRailState';
import { StockViewTabs } from '../stock_view/StockViewTabs';
import {
  DATA_FEED_DEFAULT,
  DISCOVERY_PROVIDER_DEFAULT,
} from '../constants';
import { leaveSampleView } from './sampleNav';
import { SampleDataProvider, useSampleData } from './SampleDataContext';
import { SampleModeBadge } from './SampleModeBadge';
import { sampleScannerFeed } from './sampleScannerFeed';
import { SampleWorkspaceProvider } from './SampleWorkspaceProvider';
import { SetupsStreamProvider } from '../setups/SetupsStreamContext';
import { useNavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';

/** A pop-out's Exit closes its own window; the main sample desk stays where it is. */
function closePopOut(): void {
  window.close();
}

function SampleShellInner() {
  const sample = useSampleData();
  const {
    selectedSymbol,
    setSelectedSymbol,
    traderTabs,
    traderViewActive,
    traderDeskRole,
    openStockView,
    showScannerView,
  } = useWorkspace();
  const navPage = useNavPage();
  // The sample rail opens on the sample Gappers and keeps its list in memory.
  const [focusRailStore] = useState(() => memoryFocusRailStore());
  const feed = useMemo(() => sampleScannerFeed(sample), [sample]);

  useEffect(() => {
    if (selectedSymbol) return;
    const seed =
      sample.watchlist[0]?.symbol
      ?? sample.gappers[0]?.symbol
      ?? null;
    if (seed) setSelectedSymbol(seed);
  }, [selectedSymbol, sample.watchlist, sample.gappers, setSelectedSymbol]);

  const float = traderDeskRole === 'float';
  const hasTraderDesk = traderTabs.length > 0;
  const traderUp = hasTraderDesk && (traderViewActive || float);
  const deskUp = !traderUp && navPage === 'desk';
  // The workspace slot is on screen for the full Trader and beside the Desk board.
  const showTrader = traderUp || (deskUp && hasTraderDesk);
  const branchClass = `nova-app-branch${deskUp ? ' nova-app-branch--desk' : ''}${
    deskUp && !hasTraderDesk ? ' nova-app-branch--desk-empty' : ''
  }`;

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
    onLookup: openStockView,
    showScannerSource: true,
    discoveryProvider: DISCOVERY_PROVIDER_DEFAULT,
    sampleDataActive: true,
    onSampleDataToggle: (on: boolean) => {
      if (!on) leaveSampleView();
    },
  };

  const traderSlot = hasTraderDesk && (
    <div
      className="nova-trader-desk-slot"
      hidden={!showTrader}
      aria-hidden={!showTrader}
      inert={!showTrader}
    >
      <AppErrorBoundary source="sample-trader">
        <ScannerDataContextProvider value={feed}>
          <div className={showTrader ? 'nova-shell nova-shell--ticker-detail' : 'nova-shell'}>
            <div className="main-col main-col--full main-col--trader-stack">
              <main className="ticker-detail-main">
                <StockViewTabs
                  detached={float}
                  hideFocusRail={deskUp}
                  active={showTrader}
                  focusRailStore={focusRailStore}
                />
              </main>
            </div>
          </div>
        </ScannerDataContextProvider>
      </AppErrorBoundary>
    </div>
  );

  if (float) {
    return (
      <div className="nova-app-stack nova-app-stack--float">
        <div className="nova-app-main">
          <FloatDeskChrome />
          <BotSymbolMenuHost />
          <SampleModeBadge onExit={closePopOut} />
          <div className="nova-app-branch">{traderSlot}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="nova-app-stack nova-app-stack--rail">
      <NavRail
        traderActive={traderUp}
        onOpenTrader={openStockView}
        onLeaveTrader={showScannerView}
        settings={null}
      />
      <div className="nova-app-main">
        <GlobalAppBar scanner={sampleScannerBar} />
        <SampleModeBadge onExit={leaveSampleView} />
        <div className={branchClass}>
          {traderSlot}
          {!traderUp && (
            <div className="nova-scanner-desk-slot">
              <AppErrorBoundary source="sample-dashboard">
                <NavPageHost onOpenTrader={openStockView}>
                  <SampleDashboardPage onOpenTrader={openStockView} />
                </NavPageHost>
              </AppErrorBoundary>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function SampleShell() {
  // SampleDataProvider must wrap IbkrAccountProvider so the poller serves
  // SAMPLE_IBKR_ACCOUNT_STATE (no live /api/ibkr/*). GlobalAppBar requires
  // the account context on both sample and live shells.
  return (
    <SampleDataProvider>
      <IbkrAccountProvider>
        <SampleWorkspaceProvider>
          {/* The Setups board reads the sample board; the provider never opens a socket here. */}
          <SetupsStreamProvider enabled>
            <HodMomoFixtureProvider>
              <SampleShellInner />
            </HodMomoFixtureProvider>
          </SetupsStreamProvider>
        </SampleWorkspaceProvider>
      </IbkrAccountProvider>
    </SampleDataProvider>
  );
}
