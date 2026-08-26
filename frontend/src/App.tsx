/**
 * Nova root layout — WorkspaceProvider + sample/Stock View gates + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 *
 * HOD stream owner lives here so Trader does not tear down the WS.
 * Dock UI mounts in the Scanner middle column only -- not on Trader.
 */
import { useEffect, useState } from 'react';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { GlobalAppBar } from './components/GlobalAppBar';
import { GlobalBarStatusBridge } from './components/GlobalBarStatusBridge';
import { HotkeyDispatchProvider } from './hotkeys/HotkeyDispatchContext';
import { TopOfBookProvider } from './hotkeys/TopOfBookContext';
import { HodMomoProvider } from './hod_momo/HodMomoProvider';
import { ScannerDataProvider } from './scanner/ScannerDataContext';
import { IbkrAccountProvider } from './ibkr/IbkrAccountContext';
import { TradingPrerequisitesGate } from './ibkr/TradingPrerequisitesGate';
import { DashboardPage } from './pages/DashboardPage';
import { SampleShell } from './sample_data/SampleShell';
import { isSampleView } from './sample_data/sampleNav';
import { SettingsProvider } from './settings/SettingsContext';
import { NovaOsAttentionStrip } from './strategy/NovaOsAttentionStrip';
import { useNovaOsEventAttention } from './strategy/novaOsEventAttention';
import { StockViewTabs } from './stock_view/StockViewTabs';
import { parseStockViewSymbol } from './utils/stockViewNav';
import { AppDialogHost } from './ux';
import { TraderDockLayer } from './workspace/traderDesk/TraderDockLayer';
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';
import { LayoutStoreProvider } from './workspace/useLayoutStore';
import { ModuleVisibilityProvider } from './workspace/useModuleVisibility';

function AppShell() {
  const { traderTabs, traderViewActive } = useWorkspace();
  const [sampleMode, setSampleMode] = useState(() => isSampleView());

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
    return <SampleShell />;
  }

  const hasTraderDesk = traderTabs.length > 0;
  const showTrader = hasTraderDesk && traderViewActive;
  const detached = hasTraderDesk && parseStockViewSymbol() != null;

  return (
    <IbkrAccountProvider>
      <SettingsProvider>
        <ScannerDataProvider>
          <HodMomoProvider>
            <div className="nova-app-stack">
            {/* One shared header for Scanner + Trader; status strip never clears on route. */}
            <GlobalBarStatusBridge />
            <GlobalAppBar />
            <TradingPrerequisitesGate />
            <NovaOsAttentionStrip global />
            <div className="nova-app-branch">
              <TraderDockLayer />
              {hasTraderDesk && (
                <div
                  className="nova-trader-desk-slot"
                  hidden={!showTrader}
                  aria-hidden={!showTrader}
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
                          <StockViewTabs detached={detached} />
                        </main>
                      </div>
                    </div>
                  </AppErrorBoundary>
                </div>
              )}
              {!showTrader && (
                <AppErrorBoundary source="dashboard">
                  <DashboardPage />
                </AppErrorBoundary>
              )}
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
                <AppErrorBoundary source="app-shell">
                  <AppShell />
                </AppErrorBoundary>
              </HotkeyDispatchProvider>
            </TopOfBookProvider>
          </LayoutStoreProvider>
        </ModuleVisibilityProvider>
      </WorkspaceProvider>
    </AppDialogHost>
  );
}

export default App;
