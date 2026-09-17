/**
 * Shared workspace state -- selected symbol, discovery feed, IBKR connection,
 * and Trader View tabs. Mount once in App; consumers use useWorkspace().
 * Extract/dock lives in traderDesk/ (ADR 011).
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { API_URL } from '../constants';
import { useIbkrStatus } from '../ibkr';
import type { IbkrMode } from '../ibkr/types';
import {
  useTraderDeskBinding,
  type TraderDeskRole,
  type TraderDockOffer,
  type TraderTabDragPayload,
} from './traderDesk';
import {
  WORKSPACE_CONFIG_DEFAULTS,
  parseWorkspaceConfig,
} from './workspaceConfig';

export type WorkspaceValue = {
  selectedSymbol: string | null;
  setSelectedSymbol: (sym: string | null) => void;
  discoveryProvider: string;
  setDiscoveryProvider: (provider: string) => void;
  alpacaFeed: string;
  setAlpacaFeed: (feed: string) => void;
  scannerPersistentAuthoritative: boolean;
  ibkrConnected: boolean;
  ibkrTransportConnected: boolean;
  ibkrSessionReason: string | null;
  ibkrPortsDark: boolean;
  ibkrDisconnectHint: string | null;
  /** A Second Factor prompt has sat open longer than IBC's own timeout --
   * an approval now will be silently discarded (PROBLEM_LOG 2026-08-25). */
  ibkrSecondFactorStale: boolean;
  ibkrSecondFactorAgeSec: number | null;
  ibkrMode: IbkrMode;
  ibkrGatewayMode: 'paper' | 'live' | null;
  ibkrAccountKind: string | null;
  ibkrIntentionalMode: 'paper' | 'live' | null;
  openStockView: (symbol: string) => void;
  /** Row-body click on a table with a separate ticker button (ADR 011 §7a):
   * Quote Panel only on Scanner; adds or activates a tab on Trader. */
  selectRowSymbol: (symbol: string) => void;
  extractTraderTab: (symbol: string) => void;
  acceptTraderTabDrop: (payload: TraderTabDragPayload) => boolean;
  requestDockTraderTab: (symbol: string) => void;
  traderWindowId: string;
  traderDeskRole: TraderDeskRole;
  traderDockOffer: TraderDockOffer | null;
  publishTraderTabOffer: (symbol: string) => void;
  publishTraderTabOfferEnd: () => void;
  traderTabs: string[];
  traderLiveTabs: string[];
  activeTraderSymbol: string | null;
  traderBlockNotice: string | null;
  dismissTraderBlockNotice: () => void;
  activateTraderTab: (symbol: string) => void;
  closeTraderTab: (symbol: string) => void;
  renameTraderTab: (from: string, to: string) => void;
  addTraderDraftTab: () => void;
  closeTraderView: () => void;
  traderViewActive: boolean;
  showScannerView: () => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const trader = useTraderDeskBinding(setSelectedSymbol);
  const [discoveryProvider, setDiscoveryProvider] = useState(
    WORKSPACE_CONFIG_DEFAULTS.discoveryProvider,
  );
  const [alpacaFeed, setAlpacaFeed] = useState(WORKSPACE_CONFIG_DEFAULTS.alpacaFeed);
  const [scannerPersistentAuthoritative, setScannerPersistentAuthoritative] = useState(
    WORKSPACE_CONFIG_DEFAULTS.scannerPersistentAuthoritative,
  );
  const ibkrStatus = useIbkrStatus();

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
        console.warn('[Nova] /api/config fetch failed -- keeping workspace defaults', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<WorkspaceValue>(
    () => ({
      selectedSymbol,
      setSelectedSymbol,
      discoveryProvider,
      setDiscoveryProvider,
      alpacaFeed,
      setAlpacaFeed,
      scannerPersistentAuthoritative,
      ibkrConnected: ibkrStatus.connected && !ibkrStatus.stale,
      ibkrTransportConnected: ibkrStatus.transport_connected === true,
      ibkrSessionReason: ibkrStatus.session_reason ?? null,
      ibkrPortsDark:
        ibkrStatus.preferred_port_reachable === false
        && ibkrStatus.alternate_port_reachable === false,
      ibkrDisconnectHint: ibkrStatus.disconnect_hint ?? null,
      ibkrSecondFactorStale: ibkrStatus.second_factor_stale === true,
      ibkrSecondFactorAgeSec: ibkrStatus.second_factor_age_sec ?? null,
      ibkrMode: ibkrStatus.mode,
      ibkrGatewayMode: ibkrStatus.gateway_mode ?? null,
      ibkrAccountKind: ibkrStatus.broker_account_kind ?? null,
      ibkrIntentionalMode: ibkrStatus.intentional_gateway_mode ?? null,
      openStockView: trader.openStockView,
      selectRowSymbol: trader.selectRowSymbol,
      extractTraderTab: trader.extractTraderTab,
      acceptTraderTabDrop: trader.acceptTraderTabDrop,
      requestDockTraderTab: trader.requestDockTraderTab,
      traderWindowId: trader.windowId,
      traderDeskRole: trader.role,
      traderDockOffer: trader.desk.offer,
      publishTraderTabOffer: trader.desk.publishOffer,
      publishTraderTabOfferEnd: trader.desk.publishOfferEnd,
      traderTabs: trader.traderState.tabs,
      traderLiveTabs: trader.traderState.live,
      activeTraderSymbol: trader.traderState.active,
      traderBlockNotice: trader.traderBlockNotice,
      dismissTraderBlockNotice: trader.dismissTraderBlockNotice,
      activateTraderTab: trader.activateTraderTab,
      closeTraderTab: trader.closeTraderTab,
      renameTraderTab: trader.renameTraderTab,
      addTraderDraftTab: trader.addTraderDraftTab,
      closeTraderView: trader.closeTraderView,
      traderViewActive: trader.traderViewActive,
      showScannerView: trader.showScannerView,
    }),
    [
      selectedSymbol,
      discoveryProvider,
      alpacaFeed,
      scannerPersistentAuthoritative,
      ibkrStatus.connected,
      ibkrStatus.stale,
      ibkrStatus.transport_connected,
      ibkrStatus.session_reason,
      ibkrStatus.preferred_port_reachable,
      ibkrStatus.alternate_port_reachable,
      ibkrStatus.disconnect_hint,
      ibkrStatus.second_factor_stale,
      ibkrStatus.second_factor_age_sec,
      ibkrStatus.mode,
      ibkrStatus.gateway_mode,
      ibkrStatus.broker_account_kind,
      ibkrStatus.intentional_gateway_mode,
      trader,
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
