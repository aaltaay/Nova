/**
 * Which board list to show after a HOD Momo strip row is clicked.
 *
 * The strip IS the HOD Momo list on this desk (TabModuleHost renders no
 * board for `hod_momo`), so the board keeps the current list when it already
 * holds the symbol, otherwise switches to the first scanner list that does.
 * `null` means no list holds it: the board stays put and the strip row is the
 * selection -- never an invented row.
 */
export const BOARD_LIST_SEARCH_ORDER = [
  'gappers',
  'gainers',
  'losers',
  'afterhours',
  'large_cap',
] as const;

export type BoardListId = (typeof BOARD_LIST_SEARCH_ORDER)[number];

export type BoardLists = Record<BoardListId, readonly { symbol: string }[]>;

function holds(rows: readonly { symbol: string }[], sym: string): boolean {
  return rows.some((r) => r.symbol.toUpperCase() === sym);
}

export function isBoardListId(tab: string): tab is BoardListId {
  return (BOARD_LIST_SEARCH_ORDER as readonly string[]).includes(tab);
}

export function boardListForSymbol(
  symbol: string,
  currentTab: string,
  lists: BoardLists,
): BoardListId | null {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return null;
  if (isBoardListId(currentTab) && holds(lists[currentTab], sym)) return currentTab;
  for (const id of BOARD_LIST_SEARCH_ORDER) {
    if (holds(lists[id], sym)) return id;
  }
  return null;
}
