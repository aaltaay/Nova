/**
 * Trader tab state + extract/dock actions for one OS window (ADR 011).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  TRADER_BLOCK_NOTICE_MESSAGE,
  TRADER_DOCK_NO_HOST_MESSAGE,
  TRADER_EXTRACT_BLOCKED_MESSAGE,
  TRADER_MAX_TABS,
} from '../../constantGroups/trader_view';
import { openStockViewWindow, parseStockViewSymbol } from '../../utils/stockViewNav';
import {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  addDraftTab,
  addTab,
  closeTab,
  renameTab,
  replaceActiveTab,
  type TraderTabsState,
} from '../../stock_view/traderTabsState';
import {
  canExtractFromDesk,
  claimDockTarget,
  closePolicyAfterGive,
  deskRoleFromStockView,
  isForeignTabDrag,
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
  const windowId = useMemo(() => getTraderWindowId(), []);
  const role = deskRoleFromStockView(parseStockViewSymbol());
  const [traderState, setTraderState] = useState<TraderTabsState>(boot.tabs);
  const [traderViewActive, setTraderViewActive] = useState(boot.tabs.tabs.length > 0);
  const [traderBlockNotice, setTraderBlockNotice] = useState<string | null>(boot.blockNotice);
  const traderStateRef = useRef(traderState);
  traderStateRef.current = traderState;

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

  const tryAddTab = useCallback((symbol: string): boolean => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return false;
    const { state, blocked } = addTab(traderStateRef.current, sym, TRADER_MAX_TABS);
    if (blocked) {
      showBlockNotice(sym);
      return false;
    }
    setSelectedSymbol(sym);
    setTraderViewActive(true);
    writeBlockNotice(null);
    setTraderBlockNotice(null);
    applyTraderState(state);
    return true;
  }, [applyTraderState, setSelectedSymbol, showBlockNotice]);

  /** Ticker click (ADR 011 decision 7): open the first tab, activate an
   * already-open symbol, or replace the active tab's symbol in place --
   * never adds a second tab, never blocked. `+` / dock / drop keep using
   * `tryAddTab` above. */
  const tryReplaceActive = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setSelectedSymbol(sym);
    setTraderViewActive(true);
    writeBlockNotice(null);
    setTraderBlockNotice(null);
    const urlSym = parseStockViewSymbol();
    setTraderState((prev) => {
      const fromSymbol = prev.tabs.length > 0 ? (prev.active ?? prev.tabs[0]) : null;
      const { state } = replaceActiveTab(prev, sym, TRADER_MAX_TABS);
      persistSymbolReplace(urlSym, fromSymbol, sym, state);
      return state;
    });
  }, [setSelectedSymbol]);

  const onDockRequest = useCallback((symbol: string, requestId: string) => {
    if (role !== 'host') return false;
    try {
      if (!claimDockTarget(localStorage, requestId, windowId)) return false;
    } catch {
      /* private mode -- still try to accept */
    }
    return tryAddTab(symbol);
  }, [role, tryAddTab, windowId]);

  const onGaveTab = useCallback((symbol: string) => {
    setTraderState((prev) => {
      const next = closeTab(prev, symbol);
      writeStoredTabs(next);
      const live = next.tabs.filter((t) => t !== TRADER_DRAFT_SYMBOL).length;
      if (live === 0) setTraderViewActive(false);
      if (closePolicyAfterGive(role, live) === 'close-window') {
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
    tryReplaceActive(symbol);
  }, [tryReplaceActive]);

  /** Row-body click (not the ticker) on tables that also render a
   * `SymbolSelectButton`. On Scanner, a row only loads the Quote Panel --
   * it must not steal focus into Trader. Once Trader is already showing
   * there is no Quote Panel to update, so the row instead switches the
   * active tab, same as a ticker click. */
  const selectRowSymbol = useCallback((symbol: string) => {
    if (traderViewActive) {
      tryReplaceActive(symbol);
    } else {
      setSelectedSymbol(symbol.trim().toUpperCase());
    }
  }, [traderViewActive, tryReplaceActive, setSelectedSymbol]);

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
        const next = closeTab(prev, sym);
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
    if (ok) desk.notifyDocked(payload.symbol, payload.sourceWindowId);
    return ok;
  }, [desk, tryAddTab, windowId]);

  const requestDockTraderTab = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym || role !== 'float') return;
    desk.requestDock(sym);
  }, [desk, role]);

  const activateTraderTab = useCallback((symbol: string) => {
    setTraderState((prev) => {
      const next = { tabs: prev.tabs, active: symbol.trim().toUpperCase() };
      if (!prev.tabs.includes(next.active!)) return prev;
      if (!parseStockViewSymbol()) writeStoredTabs(next);
      return next;
    });
  }, []);

  const closeTraderTab = useCallback((symbol: string) => {
    const urlSym = parseStockViewSymbol();
    const key = symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : symbol.trim().toUpperCase();
    setTraderState((prev) => {
      const next = closeTab(prev, symbol);
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
      const { state, blocked } = renameTab(prev, from, to, TRADER_MAX_TABS);
      if (blocked) {
        showBlockNotice(to);
        return prev;
      }
      persistSymbolReplace(urlSym, fromKey, toSym, state);
      return state;
    });
  }, [showBlockNotice]);

  const addTraderDraftTab = useCallback(() => {
    setTraderState((prev) => {
      const { state, blocked } = addDraftTab(prev, TRADER_MAX_TABS);
      if (blocked) {
        showBlockNotice('(new)');
        return prev;
      }
      if (!parseStockViewSymbol()) writeStoredTabs(state);
      return state;
    });
  }, [showBlockNotice]);

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
