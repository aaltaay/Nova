/**
 * Nova root layout — WorkspaceProvider + sample/Stock View gates + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 */
import { useEffect, useState } from 'react';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { HotkeyDispatchProvider } from './hotkeys/HotkeyDispatchContext';
import { TopOfBookProvider } from './hotkeys/TopOfBookContext';
import { DashboardPage } from './pages/DashboardPage';
import { StockViewPage } from './pages/StockViewPage';
import { SampleShell } from './sample_data/SampleShell';
import { isSampleView } from './sample_data/sampleNav';
import { NovaOsAttentionStrip } from './strategy/NovaOsAttentionStrip';
import { useNovaOsEventAttention } from './strategy/novaOsEventAttention';
import {
  leaveStockViewUrl,
  parseStockViewSymbol,
  replaceStockViewUrl,
} from './utils/stockViewNav';
import { AppDialogHost } from './ux';
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';
import { LayoutStoreProvider } from './workspace/useLayoutStore';
import { ModuleVisibilityProvider } from './workspace/useModuleVisibility';

function AppShell() {
  const {
    stockViewSymbol,
    setStockViewSymbol,
    setSelectedSymbol,
  } = useWorkspace();
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

  if (stockViewSymbol) {
    const detached = parseStockViewSymbol() != null;
    return (
      <AppErrorBoundary source="stock-view">
        <NovaOsAttentionStrip global />
        <div className="nova-shell nova-shell--ticker-detail">
          <div className="main-col main-col--full">
            <main className="ticker-detail-main">
              <StockViewPage
                symbol={stockViewSymbol}
                detached={detached}
                onBack={() => {
                  if (detached) {
                    leaveStockViewUrl();
                    if (window.opener) window.close();
                    else setStockViewSymbol(null);
                  } else {
                    setStockViewSymbol(null);
                  }
                }}
                onSelectSymbol={sym => {
                  setSelectedSymbol(sym);
                  setStockViewSymbol(sym);
                  if (detached) replaceStockViewUrl(sym);
                }}
              />
            </main>
          </div>
        </div>
      </AppErrorBoundary>
    );
  }

  return (
    <AppErrorBoundary source="dashboard">
      <NovaOsAttentionStrip global />
      <DashboardPage />
    </AppErrorBoundary>
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
