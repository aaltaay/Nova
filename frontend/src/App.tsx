/**
 * Nova root layout — WorkspaceProvider + sample/Stock View gates + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 *
 * HOD stream owner lives here; the dock UI mounts in the Scanner middle column
 * (and Trader main) so left rail + quote panel stay full-height side kings.
 */
import { useEffect, useState } from 'react';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { GlobalAppBar } from './components/GlobalAppBar';
import { GlobalBarStatusBridge } from './components/GlobalBarStatusBridge';
import { HotkeyDispatchProvider } from './hotkeys/HotkeyDispatchContext';
import { TopOfBookProvider } from './hotkeys/TopOfBookContext';
import { HodMomoDock } from './hod_momo/HodMomoDock';
import { HodMomoProvider } from './hod_momo/HodMomoProvider';
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
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';
import { LayoutStoreProvider } from './workspace/useLayoutStore';
import { ModuleVisibilityProvider } from './workspace/useModuleVisibility';

function AppShell() {
  const { traderTabs } = useWorkspace();
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

  const traderActive = traderTabs.length > 0;
  const detached = traderActive && parseStockViewSymbol() != null;

  return (
    <IbkrAccountProvider>
      <SettingsProvider>
        <HodMomoProvider>
          <div className="nova-app-stack">
            {/* One shared header for Scanner + Trader; status strip never clears on route. */}
            <GlobalBarStatusBridge />
            <GlobalAppBar />
            <TradingPrerequisitesGate />
            <NovaOsAttentionStrip global />
            <div className="nova-app-branch">
              {traderActive ? (
                <AppErrorBoundary source="stock-view">
                  <div className="nova-shell nova-shell--ticker-detail">
                    <div className="main-col main-col--full main-col--trader-stack">
                      <HodMomoDock />
                      <main className="ticker-detail-main">
                        <StockViewTabs detached={detached} />
                      </main>
                    </div>
                  </div>
                </AppErrorBoundary>
              ) : (
                <AppErrorBoundary source="dashboard">
                  <DashboardPage />
                </AppErrorBoundary>
              )}
            </div>
          </div>
        </HodMomoProvider>
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
