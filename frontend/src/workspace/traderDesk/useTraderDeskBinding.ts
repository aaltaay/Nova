/**
 * Trader tab state + extract/dock actions for one OS window (ADR 011).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  TRADER_BLOCK_NOTICE_MESSAGE,
  TRADER_DOCK_NO_HOST_MESSAGE,
  TRADER_EXTRACT_BLOCKED_MESSAGE,
  TRADER_MAX_LIVE_TABS,
} from '../../constantGroups/trader_view';
import { openStockViewWindow, parseStockViewSymbol } from '../../utils/stockViewNav';
import {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  activateTab,
  addDraftTab,
  addTab,
  closeTab,
  isTabLive,
  releaseOldestLive,
  renameTab,
  type TraderTabsState,
} from '../../stock_view/traderTabsState';
import {
  canExtractFromDesk,
  claimDockTarget,
  closePolicyAfterGive,
  deskRoleFromStockView,
  isForeignTabDrag,
  rememberLastHostWindow,
} from './commands';
import {
  initialTraderState,
  persistSymbolReplace,
  readStoredTabs,
  writeBlockNotice,
  writeStoredTabs,
} from './traderSession';
import { useTraderDesk } from './useTraderDesk';
import { getTraderWindowId } from './windowId';
import type { TraderTabDragPayload } from './protocol';

export function useTraderDeskBinding(setSelectedSymbol: (sym: string | null) => void) {
  const boot = initialTraderState();
  const role = deskRoleFromStockView(parseStockViewSymbol());
  const windowId = useMemo(() => getTraderWindowId(undefined, role), [role]);
  const [traderState, setTraderState] = useState<TraderTabsState>(boot.tabs);
  const [traderViewActive, setTraderViewActive] = useState(boot.tabs.tabs.length > 0);
  const [traderBlockNotice, setTraderBlockNotice] = useState<string | null>(boot.blockNotice);
  const traderStateRef = useRef(traderState);
  traderStateRef.current = traderState;

  useEffect(() => {
    if (role !== 'host') return;
    try {
      rememberLastHostWindow(localStorage, windowId);
    } catch {
      /* private mode */
    }
  }, [role, windowId]);

  const applyTraderState = useCallback((next: TraderTabsState) => {
    traderStateRef.current = next;
    setTraderState(next);
    writeStoredTabs(next);
  }, []);

  const showBlockNotice = useCallback((forSymbol: string) => {
    writeBlockNotice(forSymbol);
    setTraderBlockNotice(TRADER_BLOCK_NOTICE_MESSAGE);
  }, []);

  const dismissTraderBlockNotice = useCallback(() => {
    writeBlockNotice(null);
    setTraderBlockNotice(null);
  }, []);

  const applyOpen = useCallback((state: TraderTabsState, sym: string) => {
    setSelectedSymbol(sym);
    setTraderViewActive(true);
    writeBlockNotice(null);
    setTraderBlockNotice(null);
    applyTraderState(state);
  }, [applyTraderState, setSelectedSymbol]);

  const tryAddTab = useCallback((symbol: string): boolean => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return false;
    const { state } = addTab(traderStateRef.current, sym, TRADER_MAX_LIVE_TABS);
    applyOpen(state, sym);
    return true;
  }, [applyOpen]);

  const onDockRequest = useCallback((symbol: string, requestId: string) => {
    if (role !== 'host') return false;
    try {
      if (!claimDockTarget(localStorage, requestId, windowId)) return false;
    } catch {
      /* private mode -- still try to accept */
    }
    const ok = tryAddTab(symbol);
    if (ok) {
      try {
        rememberLastHostWindow(localStorage, windowId);
      } catch {
        /* private mode */
      }
    }
    return ok;
  }, [role, tryAddTab, windowId]);

  const onGaveTab = useCallback((symbol: string) => {
    setTraderState((prev) => {
      const next = closeTab(prev, symbol);
      writeStoredTabs(next);
      const remaining = next.tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL).length;
      if (remaining === 0) setTraderViewActive(false);
      if (closePolicyAfterGive(role, remaining) === 'close-window') {
        window.close();
      }
      return next;
    });
  }, [role]);

  const desk = useTraderDesk({
    windowId,
    role,
    onDockRequest,
    onGaveTab,
    onDockRejected: showBlockNotice,
    onDockUnanswered: () => {
      writeBlockNotice(null);
      setTraderBlockNotice(TRADER_DOCK_NO_HOST_MESSAGE);
    },
  });

  useEffect(() => {
    const urlSym = parseStockViewSymbol();
    if (!urlSym) return;
    const onUnload = () => {
      const current = parseStockViewSymbol();
      if (current) writeStoredTabs(closeTab(readStoredTabs(), current));
    };
    window.addEventListener('beforeunload', onUnload);
    return () => window.removeEventListener('beforeunload', onUnload);
  }, []);

  const openStockView = useCallback((symbol: string) => {
    tryAddTab(symbol);
  }, [tryAddTab]);

  /** Row-body click (not the ticker) on tables that also render a
   * `SymbolSelectButton`. On Scanner, a row only loads the Quote Panel --
   * it must not steal focus into Trader. Once Trader is already showing
   * there is no Quote Panel to update, so the row adds or activates. */
  const selectRowSymbol = useCallback((symbol: string) => {
    if (traderViewActive) {
      tryAddTab(symbol);
    } else {
      setSelectedSymbol(symbol.trim().toUpperCase());
    }
  }, [traderViewActive, tryAddTab, setSelectedSymbol]);

  const extractTraderTab = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym || sym === TRADER_DRAFT_SYMBOL) return;
    if (!canExtractFromDesk(role)) return;
    void openStockViewWindow(sym).then((opened) => {
      if (!opened) {
        writeBlockNotice(sym);
        setTraderBlockNotice(TRADER_EXTRACT_BLOCKED_MESSAGE);
        return;
      }
      setTraderState((prev) => {
        const wasLive = isTabLive(prev, sym);
        let next = closeTab(prev, sym);
        if (!wasLive) {
          next = releaseOldestLive(next);
        }
        writeStoredTabs(next);
        if (parseStockViewSymbol() && next.tabs.length === 0) {
          window.close();
        }
        return next;
      });
    });
  }, [role]);

  const acceptTraderTabDrop = useCallback((payload: TraderTabDragPayload) => {
    if (!isForeignTabDrag(payload.sourceWindowId, windowId)) return false;
    const ok = tryAddTab(payload.symbol);
    if (ok) {
      try {
        rememberLastHostWindow(localStorage, windowId);
      } catch {
        /* private mode */
      }
      desk.notifyDocked(payload.symbol, payload.sourceWindowId);
    }
    return ok;
  }, [desk, tryAddTab, windowId]);

  const requestDockTraderTab = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym || role !== 'float') return;
    desk.requestDock(sym);
  }, [desk, role]);

  const activateTraderTab = useCallback((symbol: string) => {
    const key = symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : symbol.trim().toUpperCase();
    setTraderState((prev) => {
      if (!prev.tabs.includes(key)) return prev;
      const next = activateTab(prev, key, TRADER_MAX_LIVE_TABS);
      if (!parseStockViewSymbol()) writeStoredTabs(next);
      return next;
    });
  }, []);

  const closeTraderTab = useCallback((symbol: string) => {
    const urlSym = parseStockViewSymbol();
    const key = symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : symbol.trim().toUpperCase();
    setTraderState((prev) => {
      let next = closeTab(prev, symbol);
      if (next.active && next.active !== TRADER_DRAFT_SYMBOL) {
        next = activateTab(next, next.active, TRADER_MAX_LIVE_TABS);
      }
      if (!urlSym) writeStoredTabs(next);
      if (next.tabs.length === 0) setTraderViewActive(false);
      return next;
    });
    if (urlSym && key === urlSym) {
      writeStoredTabs(closeTab(readStoredTabs(), urlSym));
      window.close();
    }
  }, []);

  const renameTraderTab = useCallback((from: string, to: string) => {
    const urlSym = parseStockViewSymbol();
    const toSym = to.trim().toUpperCase();
    const fromKey = from === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : from.trim().toUpperCase();
    setTraderState((prev) => {
      const { state } = renameTab(prev, from, to, TRADER_MAX_LIVE_TABS);
      persistSymbolReplace(urlSym, fromKey, toSym, state);
      return state;
    });
  }, []);

  const addTraderDraftTab = useCallback(() => {
    setTraderState((prev) => {
      const { state } = addDraftTab(prev);
      if (!parseStockViewSymbol()) writeStoredTabs(state);
      return state;
    });
  }, []);

  const closeTraderView = useCallback(() => {
    const urlSym = parseStockViewSymbol();
    if (urlSym) {
      writeStoredTabs(closeTab(readStoredTabs(), urlSym));
      window.close();
      return;
    }
    applyTraderState(EMPTY_TRADER_TABS);
    setTraderViewActive(false);
    dismissTraderBlockNotice();
  }, [applyTraderState, dismissTraderBlockNotice]);

  const showScannerView = useCallback(() => {
    setTraderViewActive(false);
  }, []);

  return {
    windowId,
    role,
    traderState,
    traderBlockNotice,
    desk,
    openStockView,
    selectRowSymbol,
    extractTraderTab,
    acceptTraderTabDrop,
    requestDockTraderTab,
    dismissTraderBlockNotice,
    activateTraderTab,
    closeTraderTab,
    renameTraderTab,
    addTraderDraftTab,
    closeTraderView,
    traderViewActive,
    showScannerView,
  };
}
