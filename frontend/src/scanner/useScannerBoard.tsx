/**
 * Everything the Scanner page needs for the board chrome, in one hook: the
 * rows after both client-side filters (with what each hid), the header
 * (title · chips · Saved · session line) and the footer (`N of M match`,
 * hidden counts, dot legend). Keeps DashboardPage to wiring.
 */
import { useMemo, type ReactNode } from 'react';
import type { LiveScannerFeed } from './ScannerDataContext';
import { isBoardListId, type BoardListId } from './boardListForSymbol';
import { ScannerBoardFooter } from './ScannerBoardFooter';
import { ScannerBoardHeader } from './ScannerBoardHeader';
import { useBoardFilters } from './useBoardFilters';
import { scanAgeKeyFor, useBoardRows, type BoardRows } from './useBoardRows';

type Feed = Pick<LiveScannerFeed, 'gappers' | 'gainers' | 'losers' | 'afterhours' | 'largeCap' | 'scanAges' | 'now'>
  & { restError?: string | null };

export interface ScannerBoard {
  rows: BoardRows['rows'];
  /** The active tab when it is a scanner-row list, else null. */
  boardList: BoardListId | null;
  /** Rows the exchange filter hid on the active list (the loud banner's count). */
  hiddenByExchange: number;
  header: ReactNode;
  footer: ReactNode;
}

export function useScannerBoard(
  scanner: Feed,
  filterByExchange: <T extends { exchange?: string | null }>(rows: T[]) => T[],
  mainTab: string,
  moduleTitle: string,
): ScannerBoard {
  const board = useBoardFilters();
  const feedLists = useMemo(
    () => ({
      gappers: scanner.gappers,
      gainers: scanner.gainers,
      losers: scanner.losers,
      afterhours: scanner.afterhours,
      large_cap: scanner.largeCap,
    }),
    [scanner.gappers, scanner.gainers, scanner.losers, scanner.afterhours, scanner.largeCap],
  );
  const boardRows = useBoardRows(feedLists, filterByExchange, board);
  const boardList = isBoardListId(mainTab) ? mainTab : null;

  const scanAgeKey = scanAgeKeyFor(mainTab);
  const lastScanTs = scanAgeKey ? scanner.scanAges[scanAgeKey] : 0;
  const scannedAgoSec = !boardList ? undefined : lastScanTs > 0 ? scanner.now - lastScanTs : null;

  const header = (
    <ScannerBoardHeader
      title={moduleTitle}
      filters={boardList ? board : null}
      scannedAgoSec={scannedAgoSec}
      feedFailure={scanner.restError ?? null}
    />
  );
  const footer = boardList ? (
    <ScannerBoardFooter
      shown={boardRows.rows[boardList].length}
      total={boardRows.totals[boardList]}
      hiddenByChips={boardRows.hiddenByChips[boardList]}
      hiddenByExchange={boardRows.hiddenByExchange[boardList]}
      noun={moduleTitle.toLowerCase()}
      onShowAll={board.clear}
    />
  ) : null;

  return {
    rows: boardRows.rows,
    boardList,
    hiddenByExchange: boardList ? boardRows.hiddenByExchange[boardList] : 0,
    header,
    footer,
  };
}
