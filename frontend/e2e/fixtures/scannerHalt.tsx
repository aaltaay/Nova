/** Browser fixture exercises the real scanner hook/socket and production Halted filter. */
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useScannerData } from '../../src/hooks/useScannerData';
import { applyBoardChips } from '../../src/scanner/boardFilters';

function Desk() {
  const scanner = useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true });
  const [haltedOnly, setHaltedOnly] = useState(false);
  const rows = applyBoardChips(scanner.gappers, new Set(haltedOnly ? ['halted'] : []));
  return <main>
    <button data-testid="halted-chip" onClick={() => setHaltedOnly(value => !value)}>Halted</button>
    <button data-testid="history" onClick={() => scanner.setHistoryDate('2026-09-23')}>History</button>
    <button data-testid="live" onClick={() => scanner.setHistoryDate(null)}>Live</button>
    <button data-testid="refresh-live" onClick={() => void scanner.fetchData()}>Refresh live</button>
    <output data-testid="history-date">{scanner.historyDate ?? 'Live'}</output>
    <output data-testid="quote-age">{scanner.scanAges.gappers}</output>
    <ul>{rows.map(row => <li data-testid={`row-${row.symbol}`} key={row.symbol}>
      {row.symbol} · {row.price} · {row.halted === true ? 'HALTED' : row.halted === false ? 'TRADING' : 'UNKNOWN'}
    </li>)}</ul>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Desk />);
