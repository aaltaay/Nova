/**
 * Persisted column order for IBKR order / position tables.
 * Drag headers to reorder; layout survives refresh via localStorage.
 */
import {
  DEFAULT_CLOSED_ORDER_COLUMNS,
  DEFAULT_POSITION_COLUMNS,
  DEFAULT_WORKING_ORDER_COLUMNS,
} from './orderTableColumns';

/**
 * Keep saved order, drop unknowns, and put a column added since the layout was saved where
 * the defaults put it: after the nearest column before it in the defaults (first when none).
 * Appending it went off the far edge of a narrow table (Sent by, 2026-10-01).
 */
export function normalizeColumnOrder(
  saved: string[] | null | undefined,
  defaults: readonly string[],
): string[] {
  const allowed = new Set(defaults);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const id of saved ?? []) {
    if (!allowed.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  defaults.forEach((id, index) => {
    if (seen.has(id)) return;
    seen.add(id);
    let at = 0;
    for (let k = index - 1; k >= 0; k -= 1) {
      const pos = out.indexOf(defaults[k]);
      if (pos >= 0) {
        at = pos + 1;
        break;
      }
    }
    out.splice(at, 0, id);
  });
  return out;
}

export function moveColumnOrder(
  order: string[],
  activeId: string,
  overId: string,
): string[] {
  const from = order.indexOf(activeId);
  const to = order.indexOf(overId);
  if (from < 0 || to < 0 || from === to) return order;
  const next = [...order];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export type OrderTableColumnStore = {
  working: string[];
  closed: string[];
  positions: string[];
};

export function defaultColumnStore(): OrderTableColumnStore {
  return {
    working: [...DEFAULT_WORKING_ORDER_COLUMNS],
    closed: [...DEFAULT_CLOSED_ORDER_COLUMNS],
    positions: [...DEFAULT_POSITION_COLUMNS],
  };
}

export function parseColumnStore(raw: string | null): OrderTableColumnStore {
  const base = defaultColumnStore();
  if (!raw) return base;
  try {
    const parsed = JSON.parse(raw) as Partial<OrderTableColumnStore>;
    return {
      working: normalizeColumnOrder(parsed.working, DEFAULT_WORKING_ORDER_COLUMNS),
      closed: normalizeColumnOrder(parsed.closed, DEFAULT_CLOSED_ORDER_COLUMNS),
      positions: normalizeColumnOrder(parsed.positions, DEFAULT_POSITION_COLUMNS),
    };
  } catch {
    return base;
  }
}

export function loadColumnStore(
  storageKey: string,
  storage: Pick<Storage, 'getItem'> = localStorage,
): OrderTableColumnStore {
  try {
    return parseColumnStore(storage.getItem(storageKey));
  } catch {
    return defaultColumnStore();
  }
}

export function saveColumnStore(
  storageKey: string,
  store: OrderTableColumnStore,
  storage: Pick<Storage, 'setItem'> = localStorage,
): void {
  try {
    storage.setItem(storageKey, JSON.stringify(store));
  } catch {
    /* quota / private mode */
  }
}
