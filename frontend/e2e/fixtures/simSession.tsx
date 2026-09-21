import { createRoot } from 'react-dom/client';
import { SimSessionHeader } from '../../src/sim/SimSessionHeader';
import { WorkspaceProvider, useWorkspace } from '../../src/workspace/WorkspaceContext';

function Desk() {
  const { openStockView, closeTraderTab, traderTabs, activeTraderSymbol } = useWorkspace();
  return <>
    <button onClick={() => openStockView('AAPL')}>Open AAPL</button>
    <button onClick={() => openStockView('IMCC')}>Open IMCC</button>
    <button onClick={() => closeTraderTab('AAPL')}>Close AAPL</button>
    <output data-testid="desk-tabs">{traderTabs.join(',')}</output>
    <output data-testid="desk-active">{activeTraderSymbol}</output>
    <SimSessionHeader active />
  </>;
}

createRoot(document.getElementById('root')!).render(<WorkspaceProvider><Desk /></WorkspaceProvider>);
