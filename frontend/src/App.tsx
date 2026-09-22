/**
 * Nova root layout — WorkspaceProvider + sample/Stock View gates + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 *
 * HOD stream owner lives here so Trader does not tear down the WS.
 * Trader stays mounted (hidden + inert) on Scanner so L2/tape stay up.
 * Dashboard unmounts on Trader. Each live pane owns a trader Orders dock.
 * The nav rail (NavRailHost) is the one navigation, beside the header and
 * the views; the dashboard slot hosts Desk / Records / Dashboard via NavPageHost.
 */
import { Suspense, useEffect, useState } from 'react';
import { LazySampleShell, LazyStockViewTabs } from './appLazy';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { GlobalAppBar } from './components/GlobalAppBar';
import { NavRailHost } from './components/NavRailHost';
import { FloatDeskChrome } from './stock_view/FloatDeskChrome';
import './styles/float-desk.css';
import { GlobalBarStatusBridge } from './components/GlobalBarStatusBridge';
import { TabLazyFallback } from './components/TabLazyFallback';
import { HotkeyDispatchProvider } from './hotkeys/HotkeyDispatchContext';
import { TopOfBookProvider } from './hotkeys/TopOfBookContext';
import { HodMomoProvider } from './hod_momo/HodMomoProvider';
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
import { TraderDockLayer } from './workspace/traderDesk/TraderDockLayer';
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';
import { LayoutStoreProvider } from './workspace/useLayoutStore';
import { ModuleVisibilityProvider } from './workspace/useModuleVisibility';

function AppShell() {
  const { traderTabs, traderViewActive, activeTraderSymbol, openStockView } = useWorkspace();
  const [sampleMode, setSampleMode] = useState(() => isSampleView());
  const hasTraderDesk = traderTabs.length > 0;
  const showTrader = hasTraderDesk && traderViewActive;
  useNovaDeskWindowTitle(sampleMode, showTrader, activeTraderSymbol);

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

  return (
    <IbkrAccountProvider>
      <SettingsProvider>
        <ScannerDataProvider>
          <HodMomoProvider>
            <div className={`nova-app-stack${detached ? ' nova-app-stack--float' : ' nova-app-stack--rail'}`}>
            {/* Parent desk keeps the rail + full chrome. Pop-out floats are child trade desks — neither. */}
            {!detached && <NavRailHost />}
            <div className="nova-app-main">
            {!detached && <GlobalBarStatusBridge />}
            {!detached && <GlobalAppBar />}
            {detached && <FloatDeskChrome />}
            {!detached && <TradingPrerequisitesGate />}
            {!detached && <GatewayDisconnectedBannerHost />}
            <MwcbBannerHost />
            <NovaOsAttentionStrip global />
            <div className="nova-app-branch">
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
                            <LazyStockViewTabs detached={detached} />
                          </Suspense>
                        </main>
                      </div>
                    </div>
                  </AppErrorBoundary>
                </div>
              )}
              {!showTrader && (
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
