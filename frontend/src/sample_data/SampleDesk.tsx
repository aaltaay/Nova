/**
 * The Desk on the sample desk (#449): the live Desk's HOD Momo dock and board
 * over the sample rows, beside the sample workspace's own Trader tabs (the
 * sample shell shows that slot next to this column, as App.tsx does for the
 * live Desk). A row click opens the symbol beside the board; a double-click
 * opens it in the full Trader.
 *
 * What differs from the live Desk is stated, never silent: the board's list
 * lives in memory (the live Desk saves it), and Record and Allowlist are
 * locked with their reasons -- the sample desk records no feed and plays no
 * bot. Watch works: the sample desk keeps its own watch list, in memory
 * (watch_list/watchListStore).
 */
import { useCallback, useMemo, useState } from 'react';
import {
  DESK_BOARD_DEFAULT_LIST,
  DESK_WORKSPACE_EMPTY_HINT,
  DESK_WORKSPACE_EMPTY_TITLE,
} from '../constantGroups/desk';
import { DeskBoard } from '../desk/DeskBoard';
import type { DeskActionLocks } from '../desk/DeskBoardRow';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { ScannerDataContextProvider } from '../scanner/ScannerDataContext';
import { TRADER_DRAFT_SYMBOL } from '../stock_view/traderTabsState';
import { useModuleVisibility, useWorkspace } from '../workspace';
import { listTabModules } from '../workspace/registry';
import '../desk/desk.css';
import { SAMPLE_DESK_ALLOWLIST_WHY, SAMPLE_DESK_RECORD_WHY } from './sampleCopy';
import { useSampleData } from './SampleDataContext';
import { sampleScannerFeed } from './sampleScannerFeed';

export const SAMPLE_DESK_ACTION_LOCKS: DeskActionLocks = {
  record: SAMPLE_DESK_RECORD_WHY,
  allowlist: SAMPLE_DESK_ALLOWLIST_WHY,
};

const NO_SYMBOLS: readonly string[] = [];
const neverAllowed = (): boolean => false;
const nothing = (): void => {};

export function SampleDesk() {
  const sample = useSampleData();
  const feed = useMemo(() => sampleScannerFeed(sample), [sample]);
  const { visibility } = useModuleVisibility();
  const {
    traderTabs,
    traderLiveTabs,
    activeTraderSymbol,
    selectedSymbol,
    openTraderTab,
    openStockView,
  } = useWorkspace();
  const [list, setList] = useState(DESK_BOARD_DEFAULT_LIST);

  // The HOD dock's News flames and the board's headline line read the scanner
  // news published per symbol; the sample dashboard is unmounted here.
  usePublishScannerNews({
    source: 'sample',
    gappers: sample.gappers,
    gainers: sample.gainers,
    losers: sample.losers,
    afterhours: sample.afterhours,
    catalysts: sample.catalysts,
  });

  const openBeside = useCallback((symbol: string) => openTraderTab(symbol), [openTraderTab]);
  const openFull = useCallback((symbol: string) => openStockView(symbol), [openStockView]);
  const modules = listTabModules().filter(m => visibility[m.id] !== false);
  const active = activeTraderSymbol && activeTraderSymbol !== TRADER_DRAFT_SYMBOL ? activeTraderSymbol : null;

  return (
    <ScannerDataContextProvider value={feed}>
      <div className="desk-page" data-testid="desk-page" data-sample="1">
        <div className="main-col main-col--scanner-stack desk-page__column">
          <HodMomoDock onOpenTrading={openBeside} />
          <DeskBoard
            feed={feed}
            list={list}
            onListChange={setList}
            modules={modules}
            selectedSymbol={active ?? selectedSymbol}
            recordingSymbols={NO_SYMBOLS}
            isAllowed={neverAllowed}
            liveTabs={traderLiveTabs}
            onOpen={openBeside}
            onPopOut={openFull}
            onRecord={nothing}
            onAllowlist={nothing}
            actionLocks={SAMPLE_DESK_ACTION_LOCKS}
          />
        </div>
        {traderTabs.length === 0 && (
          <section className="panel desk-page__empty" data-testid="desk-workspace-empty">
            <p className="desk-page__empty-title">{DESK_WORKSPACE_EMPTY_TITLE}</p>
            <p className="desk-page__calm">{DESK_WORKSPACE_EMPTY_HINT}</p>
          </section>
        )}
      </div>
    </ScannerDataContextProvider>
  );
}
