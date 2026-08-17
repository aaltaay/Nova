/**
 * Per-window sessionStorage for trader tabs / block notice.
 * Not the desk SoT -- each OS window has its own strip (ADR 011).
 */

import {
  TRADER_BLOCK_NOTICE_MESSAGE,
  TRADER_BLOCK_NOTICE_STORAGE_KEY,
  TRADER_MAX_TABS,
  TRADER_TABS_STORAGE_KEY,
} from '../../constantGroups/trader_view';
import {
  EMPTY_TRADER_TABS,
  hydrateWithSymbol,
  parseTraderTabs,
  serializeTraderTabs,
  type TraderTabsState,
} from '../../stock_view/traderTabsState';
import { parseStockViewSymbol } from '../../utils/stockViewNav';

export function readStoredTabs(): TraderTabsState {
  try {
    return parseTraderTabs(sessionStorage.getItem(TRADER_TABS_STORAGE_KEY));
  } catch {
    return EMPTY_TRADER_TABS;
  }
}

export function writeStoredTabs(state: TraderTabsState): void {
  try {
    if (state.tabs.length === 0) {
      sessionStorage.removeItem(TRADER_TABS_STORAGE_KEY);
    } else {
      sessionStorage.setItem(TRADER_TABS_STORAGE_KEY, serializeTraderTabs(state));
    }
  } catch {
    /* private mode / quota */
  }
}

export function readBlockNotice(): string | null {
  try {
    return sessionStorage.getItem(TRADER_BLOCK_NOTICE_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeBlockNotice(symbol: string | null): void {
  try {
    if (!symbol) sessionStorage.removeItem(TRADER_BLOCK_NOTICE_STORAGE_KEY);
    else sessionStorage.setItem(TRADER_BLOCK_NOTICE_STORAGE_KEY, symbol);
  } catch {
    /* ignore */
  }
}

export function initialTraderState(): {
  tabs: TraderTabsState;
  blockNotice: string | null;
} {
  const urlSym = parseStockViewSymbol();
  const stored = readStoredTabs();
  if (urlSym) {
    const { state, blocked } = hydrateWithSymbol(stored, urlSym, TRADER_MAX_TABS);
    if (blocked && !stored.tabs.includes(urlSym)) {
      return {
        tabs: { tabs: [urlSym], active: urlSym },
        blockNotice: TRADER_BLOCK_NOTICE_MESSAGE,
      };
    }
    writeStoredTabs(state);
    return {
      tabs: { tabs: [urlSym], active: urlSym },
      blockNotice: readBlockNotice() ? TRADER_BLOCK_NOTICE_MESSAGE : null,
    };
  }
  return { tabs: EMPTY_TRADER_TABS, blockNotice: null };
}
