/**
 * Shared workspace state — selected symbol, discovery feed, IBKR connection,
 * and Trader View tabs. Mount once in App; consumers use useWorkspace().
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { API_URL } from '../constants';
import {
  TRADER_BLOCK_NOTICE_MESSAGE,
  TRADER_BLOCK_NOTICE_STORAGE_KEY,
  TRADER_MAX_TABS,
  TRADER_TABS_STORAGE_KEY,
} from '../constantGroups/trader_view';
import { useIbkrStatus } from '../ibkr';
import type { IbkrMode } from '../ibkr/types';
import {
  openStockViewWindow,
  parseStockViewSymbol,
} from '../utils/stockViewNav';
import {
  EMPTY_TRADER_TABS,
  addDraftTab,
  addTab,
  closeTab,
  hydrateWithSymbol,
  parseTraderTabs,
  renameTab,
  serializeTraderTabs,
  type TraderTabsState,
} from '../stock_view/traderTabsState';
import {
  WORKSPACE_CONFIG_DEFAULTS,
  parseWorkspaceConfig,
} from './workspaceConfig';

function readStoredTabs(): TraderTabsState {
  try {
    return parseTraderTabs(sessionStorage.getItem(TRADER_TABS_STORAGE_KEY));
  } catch {
    return EMPTY_TRADER_TABS;
  }
}

function writeStoredTabs(state: TraderTabsState): void {
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

function readBlockNotice(): string | null {
  try {
    return sessionStorage.getItem(TRADER_BLOCK_NOTICE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeBlockNotice(symbol: string | null): void {
  try {
    if (!symbol) sessionStorage.removeItem(TRADER_BLOCK_NOTICE_STORAGE_KEY);
    else sessionStorage.setItem(TRADER_BLOCK_NOTICE_STORAGE_KEY, symbol);
  } catch {
    /* ignore */
  }
}

function initialTraderState(): {
  tabs: TraderTabsState;
  blockNotice: string | null;
} {
  const urlSym = parseStockViewSymbol();
  const stored = readStoredTabs();
  if (urlSym) {
    const { state, blocked } = hydrateWithSymbol(stored, urlSym, TRADER_MAX_TABS);
    if (blocked) {
      return {
        tabs: stored.tabs.length ? stored : EMPTY_TRADER_TABS,
        blockNotice: TRADER_BLOCK_NOTICE_MESSAGE,
      };
    }
    writeStoredTabs(state);
    return { tabs: state, blockNotice: readBlockNotice() ? TRADER_BLOCK_NOTICE_MESSAGE : null };
  }
  // In-app: only restore if we were already in trader (no URL) — keep empty
  // so Gappers is the scanner default; detached window always has ?view=stock.
  return { tabs: EMPTY_TRADER_TABS, blockNotice: null };
}

export type WorkspaceValue = {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
  discoveryProvider: string;
  setDiscoveryProvider: (provider: string) => void;
  alpacaFeed: string;
  setAlpacaFeed: (feed: string) => void;
  scannerPersistentAuthoritative: boolean;
  /** Product usable session (status.connected / READY). */
  ibkrConnected: boolean;
  /** Raw Gateway socket (status.transport_connected). */
  ibkrTransportConnected: boolean;
  /** Usable-session SoT reason (status.session_reason). */
  ibkrSessionReason: string | null;
  /** Both preferred + alternate API ports unreachable. */
  ibkrPortsDark: boolean;
  /** Port / login disconnect_hint from status. */
  ibkrDisconnectHint: string | null;
  /** Session mode from /api/ibkr/status -- paper | live | disconnected. */
  ibkrMode: IbkrMode;
  /** Configured Gateway port mode (may differ briefly while reconnecting). */
  ibkrGatewayMode: 'paper' | 'live' | null;
  /** Open or focus a Trader tab (detached window preferred). */
  openStockView: (symbol: string) => void;
  traderTabs: string[];
  activeTraderSymbol: string | null;
  traderBlockNotice: string | null;
  dismissTraderBlockNotice: () => void;
  activateTraderTab: (symbol: string) => void;
  closeTraderTab: (symbol: string) => void;
  renameTraderTab: (from: string, to: string) => void;
  addTraderDraftTab: () => void;
  /** Exit Trader View (in-app) — clears all tabs. */
  closeTraderView: () => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const boot = initialTraderState();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [traderState, setTraderState] = useState<TraderTabsState>(boot.tabs);
  const [traderBlockNotice, setTraderBlockNotice] = useState<string | null>(
    boot.blockNotice,
  );
  const [discoveryProvider, setDiscoveryProvider] = useState(
    WORKSPACE_CONFIG_DEFAULTS.discoveryProvider,
  );
  const [alpacaFeed, setAlpacaFeed] = useState(WORKSPACE_CONFIG_DEFAULTS.alpacaFeed);
  const [scannerPersistentAuthoritative, setScannerPersistentAuthoritative] = useState(
    WORKSPACE_CONFIG_DEFAULTS.scannerPersistentAuthoritative,
  );
  const ibkrStatus = useIbkrStatus();

  const applyTraderState = useCallback((next: TraderTabsState) => {
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

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/config`)
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (cancelled || !data) return;
        const slice = parseWorkspaceConfig(data);
        setDiscoveryProvider(slice.discoveryProvider);
        setAlpacaFeed(slice.alpacaFeed);
        setScannerPersistentAuthoritative(slice.scannerPersistentAuthoritative);
      })
      .catch((err) => {
        console.warn('[Nova] /api/config fetch failed — keeping workspace defaults', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openStockView = useCallback((symbol: string) => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setSelectedSymbol(sym);

    // Already running Trader in this window (popup was blocked earlier).
    const inAppTrader =
      traderState.tabs.length > 0 && parseStockViewSymbol() == null;
    if (inAppTrader) {
      const { state, blocked } = addTab(traderState, sym, TRADER_MAX_TABS);
      if (blocked) {
        showBlockNotice(sym);
        return;
      }
      writeBlockNotice(null);
      setTraderBlockNotice(null);
      applyTraderState(state);
      return;
    }

    const stored = readStoredTabs();
    const { state, blocked } = addTab(stored, sym, TRADER_MAX_TABS);
    if (blocked) {
      showBlockNotice(sym);
      const focusSym = stored.active ?? stored.tabs[0];
      if (focusSym) void openStockViewWindow(focusSym);
      return;
    }

    writeStoredTabs(state);
    writeBlockNotice(null);
    setTraderBlockNotice(null);

    void openStockViewWindow(sym).then(opened => {
      if (!opened) {
        // Popup blocked — run Trader in this window.
        applyTraderState(state);
      }
      // Detached: trader window hydrates from sessionStorage + URL.
    });
  }, [applyTraderState, showBlockNotice, traderState]);

  const activateTraderTab = useCallback((symbol: string) => {
    setTraderState(prev => {
      const next = { tabs: prev.tabs, active: symbol.trim().toUpperCase() };
      if (!prev.tabs.includes(next.active!)) return prev;
      writeStoredTabs(next);
      return next;
    });
  }, []);

  const closeTraderTab = useCallback((symbol: string) => {
    setTraderState(prev => {
      const next = closeTab(prev, symbol);
      writeStoredTabs(next);
      return next;
    });
  }, []);

  const renameTraderTab = useCallback((from: string, to: string) => {
    setTraderState(prev => {
      const { state, blocked } = renameTab(prev, from, to, TRADER_MAX_TABS);
      if (blocked) {
        showBlockNotice(to);
        return prev;
      }
      writeStoredTabs(state);
      return state;
    });
  }, [showBlockNotice]);

  const addTraderDraftTab = useCallback(() => {
    setTraderState(prev => {
      const { state, blocked } = addDraftTab(prev, TRADER_MAX_TABS);
      if (blocked) {
        showBlockNotice('(new)');
        return prev;
      }
      writeStoredTabs(state);
      return state;
    });
  }, [showBlockNotice]);

  const closeTraderView = useCallback(() => {
    applyTraderState(EMPTY_TRADER_TABS);
    dismissTraderBlockNotice();
  }, [applyTraderState, dismissTraderBlockNotice]);

  const value = useMemo<WorkspaceValue>(
    () => ({
      selectedSymbol,
      setSelectedSymbol,
      discoveryProvider,
      setDiscoveryProvider,
      alpacaFeed,
      setAlpacaFeed,
      scannerPersistentAuthoritative,
      ibkrConnected: ibkrStatus.connected,
      ibkrTransportConnected: ibkrStatus.transport_connected === true,
      ibkrSessionReason: ibkrStatus.session_reason ?? null,
      ibkrPortsDark:
        ibkrStatus.preferred_port_reachable === false
        && ibkrStatus.alternate_port_reachable === false,
      ibkrDisconnectHint: ibkrStatus.disconnect_hint ?? null,
      ibkrMode: ibkrStatus.mode,
      ibkrGatewayMode: ibkrStatus.gateway_mode ?? null,
      openStockView,
      traderTabs: traderState.tabs,
      activeTraderSymbol: traderState.active,
      traderBlockNotice,
      dismissTraderBlockNotice,
      activateTraderTab,
      closeTraderTab,
      renameTraderTab,
      addTraderDraftTab,
      closeTraderView,
    }),
    [
      selectedSymbol,
      discoveryProvider,
      alpacaFeed,
      scannerPersistentAuthoritative,
      ibkrStatus.connected,
      ibkrStatus.transport_connected,
      ibkrStatus.session_reason,
      ibkrStatus.preferred_port_reachable,
      ibkrStatus.alternate_port_reachable,
      ibkrStatus.disconnect_hint,
      ibkrStatus.mode,
      ibkrStatus.gateway_mode,
      openStockView,
      traderState.tabs,
      traderState.active,
      traderBlockNotice,
      dismissTraderBlockNotice,
      activateTraderTab,
      closeTraderTab,
      renameTraderTab,
      addTraderDraftTab,
      closeTraderView,
    ],
  );

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within WorkspaceProvider');
  }
  return ctx;
}
