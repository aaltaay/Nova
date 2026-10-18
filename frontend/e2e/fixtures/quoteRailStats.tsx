import { createRoot } from 'react-dom/client';
import { makeDetail } from '../../src/modules/quoteFixtures';
import { StockViewModuleCard } from '../../src/stock_view/StockViewModuleCard';
import { StockViewQuoteStats } from '../../src/stock_view/StockViewQuoteStats';
import { WorkspaceProvider } from '../../src/workspace/WorkspaceContext';
import '../../src/index.css';

// The Trader rail's Stock Quote card as StockViewDepthTape composes it, with the
// production quote stats inside. `rail` sets --ticker-trade-side-width the way
// StockViewPage does when the operator drags the rail (320-720 px), which is
// where "Rel vol (Alpaca avg)" truncated its own value (#459).
const params = new URLSearchParams(location.search);
const rail = Number(params.get('rail')) || 360;

const daily = { open: 3.88, high: 4.4, low: 3.71, close: 4.25, volume: 48_123_456, trade_count: null, vwap: null, timestamp: null };
const detail = makeDetail({
  symbol: 'GRML',
  rel_volume: 4.21,
  snapshot: {
    latest_trade: { price: 4.25, size: 100, exchange: 'Q', timestamp: '2026-10-16T14:30:00Z' },
    latest_quote: null,
    minute_bar: null,
    daily_bar: daily,
    prev_daily_bar: { ...daily, close: 1.92 },
    prev_close: 1.92,
    session_close: null,
    session_prev_close: null,
  },
  fundamentals: { ...makeDetail().fundamentals!, float_shares: 4_200_000 },
});

function Rail() {
  return (
    <div className="nova-app-branch" style={{ height: '100vh' }}>
      <div className="nova-trader-desk-slot" style={{ flex: '1 1 0', minWidth: 0, display: 'flex' }}>
        <div
          className="stock-view-page"
          style={{ flex: '1 1 0', minWidth: 0, ['--ticker-trade-side-width' as string]: `${rail}px` }}
        >
          <div className="stock-view-workspace">
            <div className="stock-view-body">
              <div className="stock-view-main" />
              <div />
              <aside className="stock-view-quote sv-rail" data-testid="stock-view-rail">
                <div className="sv-rail__depth">
                  <StockViewModuleCard title="Stock Quote" className="sv-quote-depth-card" testId="stock-view-depth-stack">
                    <StockViewQuoteStats detail={detail} />
                  </StockViewModuleCard>
                </div>
              </aside>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<WorkspaceProvider><Rail /></WorkspaceProvider>);
