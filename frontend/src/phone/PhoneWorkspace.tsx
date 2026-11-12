/**
 * The phone's own workspace. The desk's hooks read a workspace for three things: the desk's config
 * (which feed, whether the scanner is authoritative), the Gateway's status, and the Trader's tabs.
 * The first two are read here exactly as the desk reads them. The third is not the phone's to hold:
 * the desk's provider keeps the Trader's tabs and tells the bots which Level 2 lines they occupy,
 * and a second, empty copy of that list posted from here would overwrite the desk's own. So this
 * workspace has no Trader tabs and posts nothing; "open in the Trader" walks the phone's screens.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { API_URL } from '../constants';
import { useIbkrStatus } from '../ibkr';
import { WorkspaceValueProvider, type WorkspaceValue } from '../workspace';
import { ibkrStatusView } from '../workspace/ibkrStatusView';
import { WORKSPACE_CONFIG_DEFAULTS, parseWorkspaceConfig } from '../workspace/workspaceConfig';
import { cleanSymbol, go } from './phoneRoute';

const nothing = (): void => undefined;

export function PhoneWorkspaceProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState(WORKSPACE_CONFIG_DEFAULTS);
  const status = useIbkrStatus();

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/config`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data: unknown) => {
        if (!cancelled && data) setConfig(parseWorkspaceConfig(data));
      })
      .catch((err: unknown) => console.warn('[Nova phone] /api/config did not load; keeping the defaults', err));
    return () => {
      cancelled = true;
    };
  }, []);

  const view = ibkrStatusView(status);
  const value = useMemo<WorkspaceValue>(() => ({
    selectedSymbol: null,
    setSelectedSymbol: nothing,
    discoveryProvider: config.discoveryProvider,
    setDiscoveryProvider: nothing,
    alpacaFeed: config.alpacaFeed,
    setAlpacaFeed: nothing,
    scannerPersistentAuthoritative: config.scannerPersistentAuthoritative,
    ibkrConnected: status.connected && !status.stale,
    ibkrStatusKnown: view.ibkrStatusKnown,
    ibkrStatusError: view.ibkrStatusError,
    ibkrTransportConnected: view.ibkrTransportConnected,
    ibkrSessionReason: status.session_reason ?? null,
    ibkrPortsDark: view.ibkrPortsDark,
    ibkrDisconnectHint: view.ibkrDisconnectHint,
    ibkrSecondFactorStale: status.second_factor_stale === true,
    ibkrSecondFactorAgeSec: status.second_factor_age_sec ?? null,
    ibkrMode: status.mode,
    deskVenue: view.deskVenue,
    ibkrGatewayMode: status.gateway_mode ?? null,
    ibkrAccountKind: status.broker_account_kind ?? null,
    ibkrIntentionalMode: status.intentional_gateway_mode ?? null,
    openStockView: (symbol: string) => {
      const sym = cleanSymbol(symbol);
      if (sym) go({ screen: 'trade', symbol: sym });
    },
    selectRowSymbol: (symbol: string) => {
      const sym = cleanSymbol(symbol);
      if (sym) go({ screen: 'stock', symbol: sym });
    },
    extractTraderTab: nothing,
    acceptTraderTabDrop: () => false,
    requestDockTraderTab: nothing,
    traderWindowId: 'phone',
    traderDeskRole: 'float',
    traderDockOffer: null,
    publishTraderTabOffer: nothing,
    publishTraderTabOfferEnd: nothing,
    traderTabs: [],
    traderLiveTabs: [],
    traderPinnedTabs: [],
    activeTraderSymbol: null,
    traderBlockNotice: null,
    dismissTraderBlockNotice: nothing,
    activateTraderTab: nothing,
    closeTraderTab: nothing,
    pinTraderTab: nothing,
    unpinTraderTab: nothing,
    renameTraderTab: nothing,
    addTraderDraftTab: nothing,
    closeTraderView: nothing,
    traderViewActive: false,
    showScannerView: nothing,
    traderMoveLocks: null,
  }), [
    config,
    status.connected,
    status.stale,
    status.session_reason,
    status.second_factor_stale,
    status.second_factor_age_sec,
    status.mode,
    status.gateway_mode,
    status.broker_account_kind,
    status.intentional_gateway_mode,
    view.ibkrStatusKnown,
    view.ibkrStatusError,
    view.ibkrTransportConnected,
    view.ibkrPortsDark,
    view.ibkrDisconnectHint,
    view.deskVenue,
  ]);

  return <WorkspaceValueProvider value={value}>{children}</WorkspaceValueProvider>;
}
