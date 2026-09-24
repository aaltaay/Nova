import { createRoot } from 'react-dom/client';
import { DeskBoard } from '../../src/desk/DeskBoard';
import { makeLiveScannerFeedStub } from '../../src/scanner/ScannerDataContext';
import type { ScannerRow } from '../../src/types/scanner';
import '../../src/index.css';
import '../../src/desk/desk.css';

// The Desk's board column as DeskPage composes it, with the production board.
// `?list=gappers` adds "board freezes at the open"; `?hidden=1` has the
// exchange filter hide a row, the longest footer the board can show (#459).
const params = new URLSearchParams(location.search);
const list = params.get('list') ?? 'gappers';
const hideOne = params.get('hidden') === '1';

function row(symbol: string, gap: number, exchange = 'NASDAQ'): ScannerRow {
  return {
    symbol, price: 5, prev_close: 4, change_pct: gap, change_abs: 1, gap_percent: gap, volume: 1_000_000,
    rel_volume: 3, has_news: false, newest_headline_at: null, market_cap: null, float: null, short_interest: null,
    short_ratio: null, exchange,
  };
}

const rows = [row('GRML', 0.33), row('VXTL', 0.21), row('BRNQ', 0.18, 'OTC')];
const feed = makeLiveScannerFeedStub({ gappers: rows, gainers: rows });
const filterRows = <T extends ScannerRow>(input: T[]): T[] =>
  hideOne ? input.filter((r) => r.exchange !== 'OTC') : input;

function Board() {
  return (
    <div className="nova-app-branch nova-app-branch--desk" style={{ height: '100vh' }}>
      <div className="nova-scanner-desk-slot" style={{ display: 'flex' }}>
        <div className="desk-page" data-testid="desk-page">
          <div className="main-col main-col--scanner-stack desk-page__column">
            <DeskBoard
              feed={feed}
              list={list}
              onListChange={() => {}}
              selectedSymbol="GRML"
              recordingSymbols={['GRML']}
              isAllowed={(s) => s === 'GRML'}
              liveTabs={['GRML']}
              filterRows={filterRows}
              onOpen={() => {}}
              onPopOut={() => {}}
              onRecord={() => {}}
              onAllowlist={() => {}}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<Board />);
