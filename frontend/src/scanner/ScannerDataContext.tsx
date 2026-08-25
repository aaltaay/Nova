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
  /**
   * Scanner table shown in the dock, tracked separately from the main tab.
   * The dock can render Gainers while the main tab sits on frozen Gappers, so
   * both must be declared or the visible dock rows get no L1 price patches.
   */
  l1DockTab: ActiveTab | null;
  setL1DockTab: (tab: ActiveTab | null) => void;
};

const ScannerDataContext = createContext<LiveScannerFeed | null>(null);

export function ScannerDataProvider({ children }: { children: ReactNode }) {
  const { settings } = useSettings();
  const { scannerPersistentAuthoritative } = useWorkspace();
  const [l1ActiveTab, setL1ActiveTabState] = useState<ActiveTab>(DEFAULT_ACTIVE_TAB);
  const [l1DockTab, setL1DockTabState] = useState<ActiveTab | null>(null);
  const setL1ActiveTab = useCallback((tab: ActiveTab) => {
    setL1ActiveTabState(tab);
  }, []);
  const setL1DockTab = useCallback((tab: ActiveTab | null) => {
    setL1DockTabState(tab);
  }, []);
  const activeTabs = useMemo(
    () => (l1DockTab && l1DockTab !== l1ActiveTab ? [l1ActiveTab, l1DockTab] : [l1ActiveTab]),
    [l1ActiveTab, l1DockTab],
  );
  const scanner = useScannerData({
    discoveryProvider: settings.discoveryProvider,
    activeTabs,
    scannerPersistentAuthoritative,
    onActiveFeed: settings.setActiveFeed,
    onFeedFellBack: settings.setFeedFellBack,
  });
  const value = useMemo<LiveScannerFeed>(
    () => ({ ...scanner, l1ActiveTab, setL1ActiveTab, l1DockTab, setL1DockTab }),
    [scanner, l1ActiveTab, setL1ActiveTab, l1DockTab, setL1DockTab],
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
    largeCap: [],
    catalysts: [],
    tableMeta: {},
    scanAges: { gappers: 0, movers: 0, afterhours: 0, largeCap: 0 },
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
    l1DockTab: null,
    setL1DockTab: () => {},
    ...overrides,
  };
}
