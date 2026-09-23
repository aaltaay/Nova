/**
 * Whether the quote side panel is folded to its strip on the right (operator
 * ask, 2026-09-23: "collapsable to the right just like the Focus menu").
 *
 * Owner: this module. Persisted under one versioned localStorage key, like the
 * Focus rail's (`stock_view/focusRailState.ts`): an unknown version or an
 * unreadable value reads as expanded -- the default -- never a guess. Private
 * mode keeps the choice for the page's life only.
 */
import { useCallback, useState } from 'react';
import { QUOTE_PANEL_COLLAPSED_STORAGE_KEY } from '../constantGroups/scanner_board';

export const QUOTE_PANEL_STATE_VERSION = 1;

interface Stored {
  v: number;
  collapsed: boolean;
}

function safeStorage(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function readQuotePanelCollapsed(storage: Pick<Storage, 'getItem'> | null = safeStorage()): boolean {
  try {
    const raw = storage?.getItem(QUOTE_PANEL_COLLAPSED_STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as Partial<Stored> | null;
    return parsed?.v === QUOTE_PANEL_STATE_VERSION && parsed.collapsed === true;
  } catch {
    return false;
  }
}

export function writeQuotePanelCollapsed(
  collapsed: boolean,
  storage: Pick<Storage, 'setItem'> | null = safeStorage(),
): void {
  try {
    const payload: Stored = { v: QUOTE_PANEL_STATE_VERSION, collapsed };
    storage?.setItem(QUOTE_PANEL_COLLAPSED_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* private mode: the panel still folds, it just forgets on reload */
  }
}

export function useQuotePanelCollapsed(): { collapsed: boolean; toggle: () => void } {
  const [collapsed, setCollapsed] = useState(readQuotePanelCollapsed);
  const toggle = useCallback(() => {
    setCollapsed(prev => {
      writeQuotePanelCollapsed(!prev);
      return !prev;
    });
  }, []);
  return { collapsed, toggle };
}
