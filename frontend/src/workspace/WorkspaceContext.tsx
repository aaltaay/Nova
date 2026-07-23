/**
 * Shared workspace state — selected symbol, discovery feed, IBKR connection,
 * and Stock View open path. Mount once in App; consumers use useWorkspace().
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
import { useIbkrStatus } from '../ibkr';
import type { IbkrMode } from '../ibkr/types';
import {
  openStockViewWindow,
  parseStockViewSymbol,
} from '../utils/stockViewNav';
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
  /** Session mode from /api/ibkr/status — paper | live | disconnected. */
  ibkrMode: IbkrMode;
  /** Configured Gateway port mode (may differ briefly while reconnecting). */
  ibkrGatewayMode: 'paper' | 'live' | null;
  openStockView: (symbol: string) => void;
  /** When set, App renders Stock View instead of the dashboard. */
  stockViewSymbol: string | null;
  setStockViewSymbol: (sym: string | null) => void;
};

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [stockViewSymbol, setStockViewSymbol] = useState<string | null>(() =>
    parseStockViewSymbol(),
  );
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
    void openStockViewWindow(sym).then(opened => {
      if (!opened) setStockViewSymbol(sym);
    });
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
      ibkrConnected: ibkrStatus.connected,
      ibkrMode: ibkrStatus.mode,
      ibkrGatewayMode: ibkrStatus.gateway_mode ?? null,
      openStockView,
      stockViewSymbol,
      setStockViewSymbol,
    }),
    [
      selectedSymbol,
      discoveryProvider,
      alpacaFeed,
      scannerPersistentAuthoritative,
      ibkrStatus.connected,
      ibkrStatus.mode,
      ibkrStatus.gateway_mode,
      openStockView,
      stockViewSymbol,
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
