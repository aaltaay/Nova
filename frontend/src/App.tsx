/**
 * Nova root layout — WorkspaceProvider + sample/Stock View gates + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 *
 * HOD stream owner lives here so Trader does not tear down the WS.
 * Trader stays mounted (hidden + inert) on Scanner so L2/tape stay up.
 * Dashboard unmounts on Trader. Each live pane owns a trader Orders dock.
 * The nav rail (NavRailHost) is the one navigation, beside the header and
 * the views; the dashboard slot hosts Desk / Records / Dashboard via NavPageHost.
 * The Desk shows the one Trader workspace beside its board (same slot, no
 * second mount), so its tabs, sockets and charts are the Trader's own.
 */
import { Suspense, useEffect, useState } from 'react';
import { LazySampleShell, LazyStockViewTabs } from './appLazy';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { BotSymbolMenuHost } from './bot/BotSymbolMenu';
import { GlobalAppBar } from './components/GlobalAppBar';
import { NavRailHost } from './components/NavRailHost';
import { FloatDeskChrome } from './stock_view/FloatDeskChrome';
import './styles/float-desk.css';
import { GlobalBarStatusBridge } from './components/GlobalBarStatusBridge';
import { TabLazyFallback } from './components/TabLazyFallback';
import { HotkeyDispatchProvider } from './hotkeys/HotkeyDispatchContext';
import { TopOfBookProvider } from './hotkeys/TopOfBookContext';
import { HodMomoProvider } from './hod_momo/HodMomoProvider';
import { SetupsStreamProvider } from './setups/SetupsStreamContext';
import { ScannerDataProvider } from './scanner/ScannerDataContext';
import { IbkrAccountProvider } from './ibkr/IbkrAccountContext';
import { GatewayDisconnectedBannerHost } from './ibkr/GatewayDisconnectedBannerHost';
import { MwcbBannerHost } from './ibkr/MwcbBannerHost';
import { TradingPrerequisitesGate } from './ibkr/TradingPrerequisitesGate';
import { DashboardPage } from './pages/DashboardPage';
import { NavPageHost } from './pages/NavPageHost';
import { isSampleView } from './sample_data/sampleNav';
import { SettingsProvider } from './settings/SettingsContext';
import { NovaOsAttentionStrip } from './strategy/NovaOsAttentionStrip';
import { useNovaOsEventAttention } from './strategy/novaOsEventAttention';
import { parseStockViewSymbol } from './utils/stockViewNav';
import { useNovaDeskWindowTitle } from './utils/useNovaWindowTitle';
import { AdviseHost } from './advise/AdvisePanel';
import { AdviseProvider } from './advise/AdviseContext';
import { AppDialogHost } from './ux';
import { DesktopUpdateHost } from './desktop_update';
import { useFocusReport } from './focus_report/useFocusReport';
import { useNavPage } from './workspace/navRailStore';
import { TraderDockLayer } from './workspace/traderDesk/TraderDockLayer';
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';
import { LayoutStoreProvider } from './workspace/useLayoutStore';
import { ModuleVisibilityProvider } from './workspace/useModuleVisibility';

function AppShell() {
  const { traderTabs, traderViewActive, activeTraderSymbol, openStockView } = useWorkspace();
  const [sampleMode, setSampleMode] = useState(() => isSampleView());
  const navPage = useNavPage();
  const hasTraderDesk = traderTabs.length > 0;
  const traderUp = hasTraderDesk && traderViewActive;
  const deskUp = !traderUp && navPage === 'desk';
  // The workspace slot is on screen for the full Trader and beside the Desk board.
  const showTrader = traderUp || (deskUp && hasTraderDesk);
  useNovaDeskWindowTitle(sampleMode, traderUp, activeTraderSymbol);
  useFocusReport(sampleMode, traderUp, deskUp); // what this window shows, for GET /sensors/focus (ADR 033)

  useEffect(() => {
    const sync = () => setSampleMode(isSampleView());
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

  // Global — a kill switch, expired approval, or archive failure must reach
  // the attention strip regardless of which tab/page is currently mounted.
  // Skip in sample mode so the strip never pulls live events into fixtures.
  useNovaOsEventAttention(!sampleMode);

  // Hard gate: sample route never mounts live Dashboard or live Stock View.
  if (sampleMode) {
    return (
      <Suspense fallback={<TabLazyFallback />}>
        <LazySampleShell />
      </Suspense>
    );
  }

  const detached = hasTraderDesk && parseStockViewSymbol() != null;
  const branchClass = `nova-app-branch${deskUp ? ' nova-app-branch--desk' : ''}${
    deskUp && !hasTraderDesk ? ' nova-app-branch--desk-empty' : ''
  }`;

  return (
    <IbkrAccountProvider>
      <SettingsProvider>
        <ScannerDataProvider>
          <HodMomoProvider>
          <SetupsStreamProvider enabled={!detached}>
            <div className={`nova-app-stack${detached ? ' nova-app-stack--float' : ' nova-app-stack--rail'}`}>
            {/* Parent desk keeps the rail + full chrome. Pop-out floats are child trade desks — neither. */}
            {!detached && <NavRailHost />}
            <div className="nova-app-main">
            {!detached && <GlobalBarStatusBridge />}
            {!detached && <GlobalAppBar />}
            {detached && <FloatDeskChrome />}
            {/* The parent's symbol menu mounts with its app bar (GlobalBarBotRow); a pop-out
                has none, so its Trader tabs and Focus rail rows need their own host. */}
            {detached && <BotSymbolMenuHost />}
            {!detached && <TradingPrerequisitesGate />}
            {!detached && <GatewayDisconnectedBannerHost />}
            {/* Desktop app only: a newer Nova is out, and what the last update brought. */}
            {!detached && <DesktopUpdateHost />}
            <MwcbBannerHost />
            <NovaOsAttentionStrip global />
            <div className={branchClass}>
              {/* No boundary here: its .app-shell-host wrapper takes a flex share of
                  .nova-app-branch and blanked half the Trader (QA R39, regression
                  from #451). The layer renders nothing in the branch's flow. */}
              <TraderDockLayer />
              {hasTraderDesk && (
                <div
                  className="nova-trader-desk-slot"
                  hidden={!showTrader}
                  aria-hidden={!showTrader}
                  inert={!showTrader}
                >
                  <AppErrorBoundary source="stock-view">
                    <div
                      className={
                        showTrader
                          ? 'nova-shell nova-shell--ticker-detail'
                          : 'nova-shell'
                      }
                    >
                      <div className="main-col main-col--full main-col--trader-stack">
                        <main className="ticker-detail-main">
                          <Suspense fallback={<TabLazyFallback />}>
                            <LazyStockViewTabs
                              detached={detached}
                              hideFocusRail={deskUp}
                              active={showTrader}
                            />
                          </Suspense>
                        </main>
                      </div>
                    </div>
                  </AppErrorBoundary>
                </div>
              )}
              {!traderUp && (
                <div className="nova-scanner-desk-slot">
                  <AppErrorBoundary source="dashboard">
                    <NavPageHost onOpenTrader={openStockView}>
                      <DashboardPage />
                    </NavPageHost>
                  </AppErrorBoundary>
                </div>
              )}
            </div>
            </div>
            </div>
          </SetupsStreamProvider>
          </HodMomoProvider>
        </ScannerDataProvider>
      </SettingsProvider>
    </IbkrAccountProvider>
  );
}

function App() {
  return (
    <AppDialogHost>
      <WorkspaceProvider>
        <ModuleVisibilityProvider>
          <LayoutStoreProvider>
            <TopOfBookProvider>
              <HotkeyDispatchProvider>
                {/* Outer shell boundary: catches AppShell hook/provider failures
                    that page-level boundaries never see. Auto-reloads once. */}
                <AdviseProvider>
                  <AppErrorBoundary source="app-shell">
                    <AppShell />
                    <AdviseHost />
                  </AppErrorBoundary>
                </AdviseProvider>
              </HotkeyDispatchProvider>
            </TopOfBookProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>
      </WorkspaceProvider>
    </AppDialogHost>
  );
}

export default App;
