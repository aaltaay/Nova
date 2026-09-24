import { createRoot } from 'react-dom/client';
import { TopOfBookProvider } from '../../src/hotkeys/TopOfBookContext';
import { TickerTradeActionBar } from '../../src/ibkr/TickerTradeActionBar';
import { StockViewModuleCard } from '../../src/stock_view/StockViewModuleCard';
import '../../src/index.css';
import '../../src/desk/desk.css';

// The Desk's Trader rail as StockViewPage + StockViewRail compose it, with the
// production ticket inside: at <= 1600 px the Desk caps the rail at 320 px
// (desk/desk.css), which is where the ticket header's TIF clipped (#459).
const symbol = new URLSearchParams(location.search).get('symbol') ?? 'GRML';

function Rail() {
  return (
    <div className="nova-app-branch nova-app-branch--desk" style={{ height: '100vh' }}>
      <div className="nova-trader-desk-slot" style={{ flex: '1 1 0', minWidth: 0, display: 'flex' }}>
        <div className="stock-view-page" style={{ flex: '1 1 0', minWidth: 0 }}>
          <div className="stock-view-workspace">
            <div className="stock-view-body">
              <div className="stock-view-main" />
              <div />
              <aside className="stock-view-quote sv-rail" data-testid="stock-view-rail">
                <div className="sv-rail__trade-stack">
                  <StockViewModuleCard className="sv-open-card" testId="stock-view-open-card" aria-label="Trade order">
                    <TickerTradeActionBar
                      symbol={symbol}
                      mode="sim"
                      connected
                      spendStatus="paper_armed"
                      position={null}
                      summary={null}
                      referencePrice={8.6}
                      variant="rail"
                    />
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

createRoot(document.getElementById('root')!).render(<TopOfBookProvider><Rail /></TopOfBookProvider>);
