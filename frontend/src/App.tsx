/**
 * Nova root layout — Stock View gate + Dashboard shell.
 * Business logic lives in pages/hooks/components (frontend-modularity rule).
 */
import { useCallback, useState } from 'react';
import { DashboardPage } from './pages/DashboardPage';
import { StockViewPage } from './pages/StockViewPage';
import {
  leaveStockViewUrl,
  openStockViewWindow,
  parseStockViewSymbol,
  replaceStockViewUrl,
} from './utils/stockViewNav';

function App() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [stockViewSymbol, setStockViewSymbol] = useState<string | null>(() =>
    parseStockViewSymbol(),
  );

  const openStockView = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setSelectedSymbol(sym);
    void openStockViewWindow(sym).then(opened => {
      if (!opened) setStockViewSymbol(sym);
    });
  }, []);

  if (stockViewSymbol) {
    const detached = parseStockViewSymbol() != null;
    return (
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
                setStockViewSymbol(sym);
                if (detached) replaceStockViewUrl(sym);
              }}
            />
          </main>
        </div>
      </div>
    );
  }

  return (
    <DashboardPage
      selectedSymbol={selectedSymbol}
      setSelectedSymbol={setSelectedSymbol}
      onOpenTrading={openStockView}
    />
  );
}

export default App;
