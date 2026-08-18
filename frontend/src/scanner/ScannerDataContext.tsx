/**
 * AppShell owner of IBKR roster fetch + /ws/scanner.
 * Mount above Scanner/Trader so Trader dock pills keep the same rows.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useScannerData } from '../hooks/useScannerData';
import { useSettings } from '../settings/SettingsContext';
import { DEFAULT_ACTIVE_TAB, type ActiveTab } from '../workspace/registry';
import { useWorkspace } from '../workspace/WorkspaceContext';

export type LiveScannerFeed = ReturnType<typeof useScannerData> & {
  l1ActiveTab: ActiveTab;
  setL1ActiveTab: (tab: ActiveTab) => void;
};

const ScannerDataContext = createContext<LiveScannerFeed | null>(null);

export function ScannerDataProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const { scannerPersistentAuthoritative } = useWorkspace();
  const [l1ActiveTab, setL1ActiveTabState] = useState<ActiveTab>(DEFAULT_ACTIVE_TAB);
  const setL1ActiveTab = useCallback((tab: ActiveTab) => {
    setL1ActiveTabState(tab);
  }, []);
  const scanner = useScannerData({
    discoveryProvider: settings.discoveryProvider,
    activeTab: l1ActiveTab,
    scannerPersistentAuthoritative,
    onActiveFeed: settings.setActiveFeed,
    onFeedFellBack: settings.setFeedFellBack,
  });
  const value = useMemo<LiveScannerFeed>(
    () => ({ ...scanner, l1ActiveTab, setL1ActiveTab }),
    [scanner, l1ActiveTab, setL1ActiveTab],
  );
  return (
    <ScannerDataContext.Provider value={value}>{children}</ScannerDataContext.Provider>
  );
}

export function ScannerDataContextProvider({
  value,
  children,
}: {
  value: LiveScannerFeed;
  children: ReactNode;
}) {
  return (
    <ScannerDataContext.Provider value={value}>{children}</ScannerDataContext.Provider>
  );
}

export function useLiveScannerFeed(): LiveScannerFeed {
  const ctx = useContext(ScannerDataContext);
  if (!ctx) {
    throw new Error('useLiveScannerFeed must be used within ScannerDataProvider');
  }
  return ctx;
}

export function useLiveScannerFeedOptional(): LiveScannerFeed | null {
  return useContext(ScannerDataContext);
}

export function makeLiveScannerFeedStub(
  overrides: Partial<LiveScannerFeed> = {},
): LiveScannerFeed {
  return {
    mode: 'market',
    health: { status: 'ok', latency_ms: 1 },
    gappers: [],
    gainers: [],
    losers: [],
    afterhours: [],
    catalysts: [],
    tableMeta: {},
    scanAges: { gappers: 0, movers: 0, afterhours: 0 },
    now: 0,
    historyDate: null,
    setHistoryDate: () => {},
    historyDates: [],
    pricesStale: false,
    flashSymbols: {},
    lastPriceTs: 0,
    rowQuoteTs: {},
    subscriptionError: null,
    fetchData: async () => {},
    l1ActiveTab: 'gappers',
    setL1ActiveTab: () => {},
    ...overrides,
  };
}
