import { useCallback, useState } from 'react';
import { ORDER_TABLE_SORT_STORAGE_KEY } from '../constants';
import {
  cycleOrderSort,
  isOrderSortKey,
  type OrderSortMode,
  type OrderSortState,
} from './orderTableSort';

function storageKey(table: OrderSortMode): string {
  return `${ORDER_TABLE_SORT_STORAGE_KEY}.${table}`;
}

function readSort(table: OrderSortMode): OrderSortState {
  try {
    const raw = localStorage.getItem(storageKey(table));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as OrderSortState;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (level) =>
        level &&
        isOrderSortKey(level.key) &&
        (level.dir === 'asc' || level.dir === 'desc'),
    );
  } catch {
    return [];
  }
}

function writeSort(table: OrderSortMode, state: OrderSortState): void {
  try {
    if (!state.length) localStorage.removeItem(storageKey(table));
    else localStorage.setItem(storageKey(table), JSON.stringify(state));
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
