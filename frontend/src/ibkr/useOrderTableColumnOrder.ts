/**
 * Persistable column order for a single IBKR table (working / closed / positions).
 */
import { useCallback, useState } from 'react';
import { ORDER_TABLE_COLUMNS_STORAGE_KEY } from '../constants';
import {
  defaultColumnStore,
  loadColumnStore,
  moveColumnOrder,
  saveColumnStore,
  type OrderTableColumnStore,
  type OrderTableId,
} from './orderTableColumns';

function readStore(): OrderTableColumnStore {
  return loadColumnStore(ORDER_TABLE_COLUMNS_STORAGE_KEY);
}

export function useOrderTableColumnOrder(tableId: OrderTableId) {
  const [store, setStore] = useState<OrderTableColumnStore>(readStore);

  const order = store[tableId];

  const reorder = useCallback(
    (activeId: string, overId: string) => {
      setStore((prev) => {
        const nextOrder = moveColumnOrder(prev[tableId], activeId, overId);
        if (nextOrder === prev[tableId]) return prev;
        const next = { ...prev, [tableId]: nextOrder };
        saveColumnStore(ORDER_TABLE_COLUMNS_STORAGE_KEY, next);
        return next;
      });
    },
    [tableId],
  );

  const reset = useCallback(() => {
    setStore((prev) => {
      const defaults = defaultColumnStore();
      const next = { ...prev, [tableId]: defaults[tableId] };
      saveColumnStore(ORDER_TABLE_COLUMNS_STORAGE_KEY, next);
      return next;
    });
  }, [tableId]);

  return { order, reorder, reset };
}
