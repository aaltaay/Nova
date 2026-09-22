import { createRoot } from 'react-dom/client';
import { SimSessionHeader } from '../../src/sim/SimSessionHeader';
import { SimSessionStrip } from '../../src/sim/SimSessionStrip';
import { WorkspaceProvider, useWorkspace } from '../../src/workspace/WorkspaceContext';

// The production composition of a Sim desk: the SIM SESSION bar while the
// Scanner is up (it returns null once a Trader tab is open) and the
// context-strip scrubber cluster on the Trader view, exactly as
// StockViewTabs mounts it (`trailing={ibkrMode === 'sim' ? <SimSessionStrip /> : null}`).
function Desk() {
  const { openStockView, closeTraderTab, traderTabs, activeTraderSymbol, traderViewActive } = useWorkspace();
  return <>
    <button onClick={() => openStockView('AAPL')}>Open AAPL</button>
    <button onClick={() => openStockView('IMCC')}>Open IMCC</button>
    <button onClick={() => closeTraderTab('AAPL')}>Close AAPL</button>
    <output data-testid="desk-tabs">{traderTabs.join(',')}</output>
    <output data-testid="desk-active">{activeTraderSymbol}</output>
    <SimSessionHeader active />
    {traderViewActive && <SimSessionStrip />}
  </>;
}

createRoot(document.getElementById('root')!).render(<WorkspaceProvider><Desk /></WorkspaceProvider>);
