/**
 * Desk -- the Scanner + Trader hybrid (approved UX redesign). The board
 * column: the Scanner's HOD Momo dock on top, the condensed board below. The
 * Trader's own workspace (StockViewTabs, one instance) sits to the right --
 * App.tsx shows that slot beside this column, so tabs opened here are the
 * tabs the Trader shows. A row click is the open; double-click pops the
 * symbol out to the full Trader view.
 */
import { useCallback, useEffect, useState } from 'react';
import { ScannerBarBridge } from '../components/ScannerBarBridge';
import { useBotAllowlist } from '../bot/useBotAllowlist';
import { startTabRecord, stopTabRecord } from '../capture/sessionRecordStore';
import {
  DESK_SAMPLE_UNAVAILABLE,
  DESK_WORKSPACE_EMPTY_HINT,
  DESK_WORKSPACE_EMPTY_TITLE,
} from '../constantGroups/desk';
import { DeskBoard } from '../desk/DeskBoard';
import { DESK_BOARD_STATE_VERSION, readDeskBoardState, writeDeskBoardState } from '../desk/deskBoardState';
import { HodMomoDock } from '../hod_momo/HodMomoDock';
import { usePublishScannerNews } from '../hod_momo/usePublishScannerNews';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { useLiveScannerFeedOptional } from '../scanner/ScannerDataContext';
import { useSettingsOptional } from '../settings/SettingsContext';
import { TRADER_DRAFT_SYMBOL } from '../stock_view/traderTabsState';
import { DEFAULT_ACTIVE_TAB, isTabModuleId, listTabModules } from '../workspace/registry';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';
import '../desk/desk.css';

const NO_ROWS: never[] = [];

export function DeskPage() {
  const sample = useSampleDataOptional();
  if (sample) {
    return (
      <div className="desk-page desk-page--sample" data-testid="desk-page">
        <p className="desk-page__calm">{DESK_SAMPLE_UNAVAILABLE}</p>
      </div>
    );
  }
  return <LiveDesk />;
}

function LiveDesk() {
  const feed = useLiveScannerFeedOptional();
  const settings = useSettingsOptional();
  const status = useIbkrStatus();
  const { visibility } = useModuleVisibility();
  const { isAllowed, add, remove } = useBotAllowlist();
  const {
    traderTabs,
    traderLiveTabs,
    activeTraderSymbol,
    selectedSymbol,
    openTraderTab,
    openStockView,
  } = useWorkspace();
  const [list, setList] = useState(() => readDeskBoardState().list);

  const pickList = useCallback((next: string) => {
    setList(next);
    writeDeskBoardState({ v: DESK_BOARD_STATE_VERSION, list: next });
  }, []);

  // The HOD dock's News flames and the board's headline line read the scanner
  // news published per symbol; the Dashboard is unmounted here, so publish it.
  usePublishScannerNews({
    source: 'live',
    gappers: feed?.gappers ?? NO_ROWS,
    gainers: feed?.gainers ?? NO_ROWS,
    losers: feed?.losers ?? NO_ROWS,
    afterhours: feed?.afterhours ?? NO_ROWS,
    catalysts: feed?.catalysts ?? NO_ROWS,
    clear: feed?.historyDate != null,
  });

  // Declare the board's list for IBKR L1 (ADR 008): a table nobody declares
  // gets no price patches, and the board is the table on screen here.
  const l1Tab = isTabModuleId(list) ? list : DEFAULT_ACTIVE_TAB;
  const setL1ActiveTab = feed?.setL1ActiveTab;
  useEffect(() => {
    setL1ActiveTab?.(l1Tab);
  }, [l1Tab, setL1ActiveTab]);

  const modules = listTabModules().filter(m => visibility[m.id] !== false);
  const recordingSymbols =
    status.capture === true && status.recording === true ? (status.capture_symbols ?? []) : [];
  const active = activeTraderSymbol && activeTraderSymbol !== TRADER_DRAFT_SYMBOL ? activeTraderSymbol : null;
  const boardSelected = active ?? selectedSymbol;

  const onRecord = useCallback((symbol: string, start: boolean) => {
    void (start ? startTabRecord(symbol) : stopTabRecord(symbol));
  }, []);
  const onAllowlist = useCallback((symbol: string, addIt: boolean) => {
    void (addIt ? add(symbol) : remove(symbol));
  }, [add, remove]);
  return (
    <div className="desk-page" data-testid="desk-page">
      {feed && <ScannerBarBridge activeTab={l1Tab} scanner={feed} />}
      <div className="main-col main-col--scanner-stack desk-page__column">
        <HodMomoDock onOpenTrading={openTraderTab} />
        <DeskBoard
          feed={feed}
          list={list}
          onListChange={pickList}
          modules={modules}
          selectedSymbol={boardSelected}
          recordingSymbols={recordingSymbols}
          isAllowed={isAllowed}
          liveTabs={traderLiveTabs}
          filterRows={settings?.exchangeFilter?.filterRows}
          onOpen={openTraderTab}
          onPopOut={openStockView}
          onRecord={onRecord}
          onAllowlist={onAllowlist}
        />
      </div>
      {traderTabs.length === 0 && (
        <section className="panel desk-page__empty" data-testid="desk-workspace-empty">
          <p className="desk-page__empty-title">{DESK_WORKSPACE_EMPTY_TITLE}</p>
          <p className="desk-page__calm">{DESK_WORKSPACE_EMPTY_HINT}</p>
        </section>
      )}
    </div>
  );
}
