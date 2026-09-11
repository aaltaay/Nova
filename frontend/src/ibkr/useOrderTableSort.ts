import { useCallback, useState } from 'react';
import { ORDER_TABLE_SORT_STORAGE_KEY } from '../constants';
import { readPref, writePref } from '../utils/prefStore';
import {
  cycleOrderSort,
  isOrderSortKey,
  type OrderSortMode,
  type OrderSortState,
} from './orderTableSort';

function storageKey(table: OrderSortMode): string {
  return `${ORDER_TABLE_SORT_STORAGE_KEY}.${table}`;
}

function parseSortState(raw: unknown): OrderSortState | null {
  if (!Array.isArray(raw)) return null;
  return raw.filter((level): level is OrderSortState[number] => {
    if (!level || typeof level !== 'object') return false;
    const item = level as { key?: unknown; dir?: unknown };
    return (
      typeof item.key === 'string' &&
      isOrderSortKey(item.key) &&
      (item.dir === 'asc' || item.dir === 'desc')
    );
  });
}

function readSort(table: OrderSortMode): OrderSortState {
  return readPref(storageKey(table), [], parseSortState);
}

function writeSort(table: OrderSortMode, state: OrderSortState): void {
  try {
    if (!state.length) localStorage.removeItem(storageKey(table));
    else writePref(storageKey(table), state);
  } catch {
    /* private mode */
  }
}

/** Persisted click / Shift+click sort stack for an order table. */
export function useOrderTableSort(table: OrderSortMode) {
  const [sortState, setSortState] = useState<OrderSortState>(() =>
    readSort(table),
  );

  const onSortColumn = useCallback(
    (columnId: string, additive: boolean) => {
      if (!isOrderSortKey(columnId)) return;
      setSortState((prev) => {
        const next = cycleOrderSort(prev, columnId, additive);
        writeSort(table, next);
        return next;
      });
    },
    [table],
  );

  const clearSort = useCallback(() => {
    setSortState([]);
    writeSort(table, []);
  }, [table]);

  return { sortState, onSortColumn, clearSort };
}
