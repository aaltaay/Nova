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
  addTab,
  closeTab,
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

/**
 * Shared persistence for "the target symbol changed here" (rename commit or
 * ticker-click replace, ADR 011 decision 7). A float window's sessionStorage
 * carries a copy of the host's multi-symbol registry from extraction time
 * even though its own tab strip shows one tab, so a target change closes the
 * old symbol in that stored registry (not just this window's `nextState`) --
 * otherwise a later dock-back would resurrect the stale symbol.
 */
export function persistSymbolReplace(
  urlSym: string | null,
  fromSymbol: string | null,
  toSymbol: string,
  nextState: TraderTabsState,
): void {
  if (urlSym && toSymbol && fromSymbol === urlSym) {
    const registry = closeTab(readStoredTabs(), urlSym);
    const merged = addTab(registry, toSymbol, TRADER_MAX_TABS);
    if (!merged.blocked) writeStoredTabs(merged.state);
    return;
  }
  if (!urlSym) writeStoredTabs(nextState);
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
