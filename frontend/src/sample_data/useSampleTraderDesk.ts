/**
 * The sample desk's Trader tabs (#449): the live desk's tab rules
 * (stock_view/traderTabsState -- preview tabs, pins, three live slots) held in
 * memory for this window only. Nothing here touches the operator's saved tabs,
 * the dock bus or the bot's focus list: the live binding
 * (workspace/traderDesk/useTraderDeskBinding) owns those, and stays out of the
 * sample route.
 *
 * The URL follows the active tab so a reload reopens it: the main window's
 * `?view=sample&symbol=X` while the Trader shows, a pop-out's
 * `?view=sample&symbol=X&popout=1`. A pop-out opens with its one tab, pinned,
 * and closes its window when that tab closes.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TRADER_EXTRACT_BLOCKED_MESSAGE, TRADER_MAX_LIVE_TABS } from '../constantGroups/trader_view';
import {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  activateTab,
  addDraftTab,
  addTab,
  closeTab,
  isTabLive,
  pinTab,
  releaseOldestLive,
  renameTab,
  unpinTab,
  type TraderTabsState,
} from '../stock_view/traderTabsState';
import type { TraderMoveLocks } from '../workspace';
import type { TraderTabDragPayload } from '../workspace/traderDesk';
import {
  SAMPLE_TRADER_DOCK_WHY,
  SAMPLE_TRADER_STRIP_TITLE,
  SAMPLE_TRADER_STRIP_TITLE_NO_POPOUT,
} from './sampleCopy';
import {
  isSamplePopOut,
  isSampleView,
  leaveSampleTraderUrl,
  parseSampleSymbol,
  replaceSamplePopOutUrl,
  replaceSampleTraderUrl,
} from './sampleNav';
import { openSamplePopOut, samplePopOutWhy } from './samplePopOut';

/** The sample desk's window id: it never matches a live window, and no drag carries it. */
export const SAMPLE_TRADER_WINDOW_ID = 'nova-sample-desk';

/** A symbol in the URL opens as the one tab, pinned: it was asked for by name. */
export function sampleSeedTabs(symbol: string | null): TraderTabsState {
  const sym = symbol?.trim().toUpperCase();
  return sym ? { tabs: [sym], active: sym, live: [sym], pinned: [sym] } : EMPTY_TRADER_TABS;
}

function tabKey(symbol: string): string {
  return symbol === TRADER_DRAFT_SYMBOL ? TRADER_DRAFT_SYMBOL : symbol.trim().toUpperCase();
}

function closeWindow(): void {
  window.close();
}

export function useSampleTraderDesk(setSelectedSymbol: (sym: string | null) => void) {
  const [role] = useState<'host' | 'float'>(() => (isSamplePopOut() ? 'float' : 'host'));
  const [state, setState] = useState<TraderTabsState>(() => sampleSeedTabs(parseSampleSymbol()));
  const [viewActive, setViewActive] = useState(() => parseSampleSymbol() != null);
  const [blockNotice, setBlockNotice] = useState<string | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const float = role === 'float';

  const apply = useCallback((next: TraderTabsState) => {
    stateRef.current = next;
    setState(next);
    return next;
  }, []);

  const afterClose = useCallback((next: TraderTabsState) => {
    if (next.tabs.length > 0) return;
    if (float) closeWindow();
    else setViewActive(false);
  }, [float]);

  const openStockView = useCallback((symbol: string, opts?: { pin?: boolean; from?: string }) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    let { state: next } = addTab(stateRef.current, sym, TRADER_MAX_LIVE_TABS, { replacePreview: !opts?.pin });
    if (opts?.pin) next = pinTab(next, sym);
    apply(next);
    setSelectedSymbol(sym);
    setViewActive(true);
    setBlockNotice(null);
  }, [apply, setSelectedSymbol]);

  const openTraderTab = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    apply(addTab(stateRef.current, sym, TRADER_MAX_LIVE_TABS).state);
    setSelectedSymbol(sym);
  }, [apply, setSelectedSymbol]);

  const selectRowSymbol = useCallback((symbol: string) => {
    if (viewActive) openStockView(symbol);
    else setSelectedSymbol(symbol.trim().toUpperCase());
  }, [openStockView, setSelectedSymbol, viewActive]);

  const extractTraderTab = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym || sym === TRADER_DRAFT_SYMBOL || float || samplePopOutWhy()) return;
    if (!openSamplePopOut(sym)) {
      setBlockNotice(TRADER_EXTRACT_BLOCKED_MESSAGE);
      return;
    }
    const prev = stateRef.current;
    let next = closeTab(prev, sym);
    if (!isTabLive(prev, sym)) next = releaseOldestLive(next);
    afterClose(apply(next));
  }, [afterClose, apply, float]);

  const activateTraderTab = useCallback((symbol: string) => {
    const key = tabKey(symbol);
    if (!stateRef.current.tabs.includes(key)) return;
    apply(activateTab(stateRef.current, key, TRADER_MAX_LIVE_TABS));
  }, [apply]);

  const closeTraderTab = useCallback((symbol: string) => {
    let next = closeTab(stateRef.current, tabKey(symbol));
    if (next.active && next.active !== TRADER_DRAFT_SYMBOL) {
      next = activateTab(next, next.active, TRADER_MAX_LIVE_TABS);
    }
    afterClose(apply(next));
  }, [afterClose, apply]);

  const pinTraderTab = useCallback((symbol: string) => {
    apply(pinTab(stateRef.current, symbol));
  }, [apply]);

  const unpinTraderTab = useCallback((symbol: string) => {
    apply(unpinTab(stateRef.current, symbol));
  }, [apply]);

  const renameTraderTab = useCallback((from: string, to: string) => {
    apply(renameTab(stateRef.current, from, to, TRADER_MAX_LIVE_TABS).state);
  }, [apply]);

  const addTraderDraftTab = useCallback(() => {
    apply(addDraftTab(stateRef.current).state);
  }, [apply]);

  const closeTraderView = useCallback(() => {
    if (float) {
      closeWindow();
      return;
    }
    apply(EMPTY_TRADER_TABS);
    setViewActive(false);
    setBlockNotice(null);
  }, [apply, float]);

  const showScannerView = useCallback(() => setViewActive(false), []);
  const dismissTraderBlockNotice = useCallback(() => setBlockNotice(null), []);
  // Sample tabs never cross into another window: no drop, no dock, no offer (traderMoveLocks says why).
  const acceptTraderTabDrop = useCallback((_payload: TraderTabDragPayload) => false, []);
  const noMove = useCallback((_symbol?: string) => {}, []);

  // The URL follows the active tab, so a reload reopens it.
  const activeSymbol = state.active && state.active !== TRADER_DRAFT_SYMBOL ? state.active : null;
  useEffect(() => {
    if (!isSampleView()) return;
    if (float) {
      if (activeSymbol) replaceSamplePopOutUrl(activeSymbol);
    } else if (viewActive && activeSymbol) {
      replaceSampleTraderUrl(activeSymbol);
    } else if (!viewActive && parseSampleSymbol()) {
      leaveSampleTraderUrl();
    }
  }, [activeSymbol, float, viewActive]);

  // Back / forward inside the sample route: the URL's symbol is the Trader's.
  useEffect(() => {
    if (float) return undefined;
    const sync = () => {
      if (!isSampleView()) return;
      const sym = parseSampleSymbol();
      if (sym) openStockView(sym, { pin: true });
      else setViewActive(false);
    };
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, [float, openStockView]);

  const moveLocks = useMemo<TraderMoveLocks>(() => {
    const extract = samplePopOutWhy();
    return {
      title: extract ? SAMPLE_TRADER_STRIP_TITLE_NO_POPOUT : SAMPLE_TRADER_STRIP_TITLE,
      dock: SAMPLE_TRADER_DOCK_WHY,
      extract,
    };
  }, []);

  return {
    role,
    windowId: SAMPLE_TRADER_WINDOW_ID,
    traderState: state,
    traderViewActive: viewActive,
    traderBlockNotice: blockNotice,
    moveLocks,
    openStockView,
    openTraderTab,
    selectRowSymbol,
    extractTraderTab,
    acceptTraderTabDrop,
    requestDockTraderTab: noMove,
    publishTraderTabOffer: noMove,
    publishTraderTabOfferEnd: noMove,
    dismissTraderBlockNotice,
    activateTraderTab,
    closeTraderTab,
    pinTraderTab,
    unpinTraderTab,
    renameTraderTab,
    addTraderDraftTab,
    closeTraderView,
    showScannerView,
  };
}
