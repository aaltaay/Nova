import { createRoot } from 'react-dom/client';
import { SimSessionHeader } from '../../src/sim/SimSessionHeader';
import { WorkspaceProvider, useWorkspace } from '../../src/workspace/WorkspaceContext';

function Desk() {
  const { openStockView, closeTraderTab, traderTabs, activeTraderSymbol } = useWorkspace();
  return <>
    <button onClick={() => openStockView('SIM1')}>Open SIM1</button>
    <button onClick={() => openStockView('IMCC')}>Open IMCC</button>
    <button onClick={() => closeTraderTab('SIM1')}>Close SIM1</button>
    <output data-testid="desk-tabs">{traderTabs.join(',')}</output>
    <output data-testid="desk-active">{activeTraderSymbol}</output>
    <SimSessionHeader active />
  </>;
}

createRoot(document.getElementById('root')!).render(<WorkspaceProvider><Desk /></WorkspaceProvider>);
