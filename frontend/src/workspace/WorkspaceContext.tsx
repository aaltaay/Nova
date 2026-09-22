/**
 * Shared workspace state -- selected symbol, discovery feed, IBKR connection,
 * and Trader View tabs. Mount once in App; consumers use useWorkspace().
 * Extract/dock lives in traderDesk/ (ADR 011).
 */
import {
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { hmrStableContext } from '../utils/hmrStableContext';
import { API_URL } from '../constants';
import { useIbkrStatus } from '../ibkr';
import type { DeskVenue } from '../constantGroups/desk_venue';
import type { IbkrMode } from '../ibkr/types';
import { ibkrStatusView } from './ibkrStatusView';
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
  /**
   * True once /api/ibkr/status answered and the answer is current. While the
   * first poll is pending or the route is failing, nothing is known about IB
   * Gateway -- the transport, ports and hint below are then undefined / false
   * / null, never a proven outage (QA D10).
   */
  ibkrStatusKnown: boolean;
  /** Why the status is not known: "HTTP 500", "no answer"... null when known or still loading. */
  ibkrStatusError: string | null;
  /** Raw Gateway socket; undefined while the status is not known. */
  ibkrTransportConnected: boolean | undefined;
  ibkrSessionReason: string | null;
  ibkrPortsDark: boolean;
  ibkrDisconnectHint: string | null;
  /** A Second Factor prompt has sat open longer than IBC's own timeout --
   * an approval now will be silently discarded (PROBLEM_LOG 2026-08-25). */
  ibkrSecondFactorStale: boolean;
  ibkrSecondFactorAgeSec: number | null;
  /**
   * The status `mode`: on Live it is the Gateway port label ('paper' on the
   * by-hand paper Gateway), so it is not the desk venue -- read `deskVenue`.
   */
  ibkrMode: IbkrMode;
  /** ADR 020's one truth for Live / Paper / Sim: the status `venue` (then `mode`). */
  deskVenue: DeskVenue | null;
  ibkrGatewayMode: 'paper' | 'live' | null;
  ibkrAccountKind: string | null;
  ibkrIntentionalMode: 'paper' | 'live' | null;
  openStockView: (symbol: string) => void;
  /** Desk board row click: add or activate the tab and select the symbol
   * without switching to the full Trader view (the Desk shows the workspace
   * beside its board). */
  openTraderTab: (symbol: string) => void;
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

const WorkspaceContext = hmrStableContext<WorkspaceValue>(import.meta.hot, 'WorkspaceContext');

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

  const statusView = ibkrStatusView(ibkrStatus);
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
      ibkrStatusKnown: statusView.ibkrStatusKnown,
      ibkrStatusError: statusView.ibkrStatusError,
      ibkrTransportConnected: statusView.ibkrTransportConnected,
      ibkrSessionReason: ibkrStatus.session_reason ?? null,
      ibkrPortsDark: statusView.ibkrPortsDark,
      ibkrDisconnectHint: statusView.ibkrDisconnectHint,
      ibkrSecondFactorStale: ibkrStatus.second_factor_stale === true,
      ibkrSecondFactorAgeSec: ibkrStatus.second_factor_age_sec ?? null,
      ibkrMode: ibkrStatus.mode,
      deskVenue: statusView.deskVenue,
      ibkrGatewayMode: ibkrStatus.gateway_mode ?? null,
      ibkrAccountKind: ibkrStatus.broker_account_kind ?? null,
      ibkrIntentionalMode: ibkrStatus.intentional_gateway_mode ?? null,
      openStockView: trader.openStockView,
      openTraderTab: trader.openTraderTab,
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
      statusView.ibkrStatusKnown,
      statusView.ibkrStatusError,
      statusView.ibkrTransportConnected,
      statusView.ibkrPortsDark,
      statusView.ibkrDisconnectHint,
      statusView.deskVenue,
      ibkrStatus.session_reason,
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
