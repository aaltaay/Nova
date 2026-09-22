import { createRoot } from 'react-dom/client';
import { WorkspaceProvider, ModuleVisibilityProvider, useWorkspace } from '../../src/workspace';
import { SimSessionHeader } from '../../src/sim/SimSessionHeader';
import { SimSessionStrip } from '../../src/sim/SimSessionStrip';
import { StockViewDepthTape } from '../../src/stock_view/StockViewDepthTape';
import { useHistoricalSnapshot } from '../../src/sim/useHistoricalSnapshot';
import type { TickerDetail } from '../../src/types/ticker';
import '../../src/index.css';

// Production components with a deterministic read-only API supplied by the test.
// The second consumer models the ticker-detail/header subscription in the desk.
// The Sim chrome follows the app: the SIM SESSION bar until a Trader tab opens
// (Load replay opens one), then the context-strip cluster StockViewTabs mounts.
function Desk() {
  const { traderViewActive } = useWorkspace();
  const snapshot = useHistoricalSnapshot('IMCC', true);
  return <><SimSessionHeader active />
    {traderViewActive && <SimSessionStrip />}
    <main className="stock-view-page" style={{ padding: 16 }}>
      <p>Replay performance fixture · IMCC · 200 reached prints</p>
      <output data-testid="replay-count">{snapshot?.prints.length ?? 0}</output>
      <div style={{ width: 620, height: 560, display: 'flex' }}>
        <StockViewDepthTape selectedSymbol="IMCC" detail={{symbol: 'IMCC'} as TickerDetail} />
      </div>
    </main></>;
}
createRoot(document.getElementById('root')!).render(
  <WorkspaceProvider><ModuleVisibilityProvider><Desk /></ModuleVisibilityProvider></WorkspaceProvider>,
);
