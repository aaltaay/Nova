/**
 * Nova root layout — WorkspaceProvider + Stock View gate + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 */
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { DashboardPage } from './pages/DashboardPage';
import { StockViewPage } from './pages/StockViewPage';
import { NovaOsAttentionStrip } from './strategy/NovaOsAttentionStrip';
import { useNovaOsEventAttention } from './strategy/novaOsEventAttention';
import {
  leaveStockViewUrl,
  parseStockViewSymbol,
  replaceStockViewUrl,
} from './utils/stockViewNav';
import { useWorkspace, WorkspaceProvider } from './workspace/WorkspaceContext';

function AppShell() {
  const {
    stockViewSymbol,
    setStockViewSymbol,
    setSelectedSymbol,
  } = useWorkspace();

  // Global — a kill switch, expired approval, or archive failure must reach
  // the attention strip regardless of which tab/page is currently mounted.
  useNovaOsEventAttention(true);

  if (stockViewSymbol) {
    const detached = parseStockViewSymbol() != null;
    return (
      <AppErrorBoundary source="stock-view">
        <NovaOsAttentionStrip global />
        <div className="container container--ticker-detail">
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
    <WorkspaceProvider>
      <AppShell />
    </WorkspaceProvider>
  );
}

export default App;
