/**
 * Scanner-only patches for the shared GlobalAppBar status strip:
 * price freshness + backend-restart refresh. Never clears the bar on unmount.
 */
import { useEffect, useRef } from 'react';
import { useScannerData } from '../hooks/useScannerData';
import { useSettings } from '../settings/SettingsContext';
import { scanAgeForTab } from '../utils/scanAge';
import { tabUsesScannerPricePatch, type ActiveTab } from '../workspace/registry';
import {
  patchScannerBarProps,
  useScannerBarProps,
} from './scannerBarStore';

type Props = {
  activeTab: ActiveTab;
  scanner: ReturnType<typeof useScannerData>;
};

export function ScannerBarBridge({ activeTab, scanner }: Props) {
  const { settings } = useSettings();
  const bar = useScannerBarProps();
  const refreshRef = useRef<() => void>(() => {});
  refreshRef.current = () => {
    void scanner.fetchData();
  };

  // Keep scanner history in sync with the shared bar (owned by AppShell bridge).
  useEffect(() => {
    if (!bar) return;
    if (bar.historyDate === scanner.historyDate) return;
    scanner.setHistoryDate(bar.historyDate);
    if (bar.historyDate === null) void scanner.fetchData();
  }, [bar, scanner.historyDate, scanner.setHistoryDate, scanner.fetchData]);

  useEffect(() => {
    const showFresh =
      tabUsesScannerPricePatch(activeTab) &&
      settings.discoveryProvider === 'ibkr' &&
      scanner.historyDate === null;
    const lastScan = scanAgeForTab(activeTab, scanner.scanAges);
    const ts = scanner.lastPriceTs > 0 ? scanner.lastPriceTs : lastScan;
    const secondsAgo =
      showFresh && ts > 0 ? Math.max(0, Math.floor(scanner.now - ts)) : null;

    patchScannerBarProps({
      secondsAgo,
      pricesStale: showFresh && scanner.pricesStale,
      onBackendStarted: () => refreshRef.current(),
    });
  }, [
    activeTab,
    scanner.historyDate,
    scanner.lastPriceTs,
    scanner.pricesStale,
    scanner.scanAges,
    scanner.now,
    settings.discoveryProvider,
  ]);

  return null;
}
