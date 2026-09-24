/** One table's click-to-sort state, remembered per table in the browser. */
import { useCallback, useMemo, useState } from 'react';
import { TABLE_SORT_STORAGE_PREFIX } from '../constants';
import { readPref, writePref } from '../utils/prefStore';
import {
  firstSortDir,
  nextTableSort,
  parseTableSort,
  sortTableRows,
  type SortColumns,
  type TableSort,
} from './tableSort';

function storageKey(tableId: string): string {
  return `${TABLE_SORT_STORAGE_PREFIX}.${tableId}`;
}

function readSort(tableId: string | null): TableSort | null {
  if (!tableId) return null;
  return readPref(storageKey(tableId), null, parseTableSort);
}

function writeSort(tableId: string | null, sort: TableSort | null): void {
  if (!tableId) return;
  try {
    if (sort) writePref(storageKey(tableId), sort);
    else localStorage.removeItem(storageKey(tableId));
  } catch {
    /* private mode: the sort still holds for this page */
  }
}

export interface TableSortState<T> {
  /** The rows in the chosen order (the rows as given while unsorted). */
  rows: T[];
  sort: TableSort | null;
  /** A header click on `key`: first direction, flip, then the table's own order. */
  onSort: (key: string) => void;
}

/**
 * `tableId` names the table in storage (`null`: not remembered). Keep
 * `columns` stable -- a module constant, or `useMemo` when a column reads
 * something outside the row.
 */
export function useTableSort<T>(
  tableId: string | null,
  rows: readonly T[],
  columns: SortColumns<T>,
): TableSortState<T> {
  const [sort, setSort] = useState<TableSort | null>(() => readSort(tableId));

  const onSort = useCallback((key: string) => {
    const next = nextTableSort(sort, key, firstSortDir(columns[key], rows));
    setSort(next);
    writeSort(tableId, next);
  }, [sort, columns, rows, tableId]);

  const sorted = useMemo(() => sortTableRows(rows, sort, columns), [rows, sort, columns]);
  return { rows: sorted, sort, onSort };
}
