/**
 * Live Scanner: publish scanner status into GlobalAppBar so the header is one row.
 */
import { useEffect, useRef } from 'react';
import { setScannerBarProps } from '../components/scannerBarBridge';
import { useScannerData } from '../hooks/useScannerData';
import { useSettings } from '../settings/SettingsContext';
import { scanAgeForTab } from '../utils/scanAge';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { DEFAULT_ACTIVE_TAB, tabUsesScannerPricePatch, type ActiveTab } from '../workspace/registry';
import { enterSampleView } from '../sample_data/sampleNav';

type Props = {
  activeTab: ActiveTab;
  scanner: ReturnType<typeof useScannerData>;
  onHistoryChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
};

export function ScannerBarBridge({ activeTab, scanner, onHistoryChange }: Props) {
  void activeTab;
  const { settings } = useSettings();
  const { ibkrConnected, ibkrMode, ibkrGatewayMode, setSelectedSymbol } = useWorkspace();
  const refreshRef = useRef<() => void>(() => {});
  refreshRef.current = () => {
    void scanner.fetchData();
  };

  useEffect(() => {
    const mainTab: ActiveTab = DEFAULT_ACTIVE_TAB;
    const showFresh =
      tabUsesScannerPricePatch(mainTab) &&
      settings.discoveryProvider === 'ibkr' &&
      scanner.historyDate === null;
    const lastScan = scanAgeForTab(mainTab, scanner.scanAges);
    const ts = scanner.lastPriceTs > 0 ? scanner.lastPriceTs : lastScan;
    const secondsAgo = showFresh && ts > 0
      ? Math.max(0, Math.floor(scanner.now - ts))
      : null;

    setScannerBarProps({
      mode: scanner.mode,
      health: scanner.health,
      activeFeed: settings.activeFeed,
      feedFellBack: settings.feedFellBack,
      secondsAgo,
      pricesStale: showFresh && scanner.pricesStale,
      ibkrConnected,
      ibkrMode,
      ibkrGatewayMode,
      historyDate: scanner.historyDate,
      historyDates: scanner.historyDates,
      onHistoryChange,
      onLookup: setSelectedSymbol,
      showScannerSource: mainTab !== 'trading' && mainTab !== 'reports',
      discoveryProvider: settings.discoveryProvider,
      onBackendStarted: () => refreshRef.current(),
      sampleDataActive: false,
      onSampleDataToggle: (on: boolean) => {
        if (on) enterSampleView();
      },
    });

    return () => setScannerBarProps(null);
  }, [
    activeTab,
    scanner.mode,
    scanner.health,
    scanner.historyDate,
    scanner.historyDates,
    scanner.lastPriceTs,
    scanner.pricesStale,
    scanner.scanAges,
    scanner.now,
    settings.activeFeed,
    settings.feedFellBack,
    settings.discoveryProvider,
    ibkrConnected,
    ibkrMode,
    ibkrGatewayMode,
    setSelectedSymbol,
    onHistoryChange,
  ]);

  return null;
}
