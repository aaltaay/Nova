/**
 * Hard-gated sample route shell — never mounts live DashboardPage / scanner hooks.
 * ?view=sample → dashboard fixtures; ?view=sample&symbol=X → Trader with sample ticker.
 */
import { useCallback, useEffect, useState } from 'react';
import { AppErrorBoundary } from '../components/AppErrorBoundary';
import { StockViewPage } from '../pages/StockViewPage';
import { SampleDashboardPage } from '../pages/SampleDashboardPage';
import {
  leaveSampleTraderUrl,
  leaveSampleView,
  parseSampleSymbol,
  replaceSampleTraderUrl,
} from './sampleNav';
import { SampleDataProvider } from './SampleDataContext';

function SampleShellInner() {
  const [traderSymbol, setTraderSymbol] = useState<string | null>(() => parseSampleSymbol());

  useEffect(() => {
    const sync = () => setTraderSymbol(parseSampleSymbol());
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);

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

  if (traderSymbol) {
    return (
      <AppErrorBoundary source="sample-trader">
        <div className="nova-shell nova-shell--ticker-detail">
          <div className="main-col main-col--full">
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
    );
  }

  return (
    <AppErrorBoundary source="sample-dashboard">
      <SampleDashboardPage onOpenTrader={openTrader} onLeaveSample={leaveSampleView} />
    </AppErrorBoundary>
  );
}

export function SampleShell() {
  return (
    <SampleDataProvider>
      <SampleShellInner />
    </SampleDataProvider>
  );
}
