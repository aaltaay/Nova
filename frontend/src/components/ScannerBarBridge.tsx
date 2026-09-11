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
  const {
    fetchData,
    historyDate,
    lastPriceTs,
    now,
    pricesStale,
    scanAges,
    setHistoryDate,
  } = scanner;
  const refreshRef = useRef<() => void>(() => {});
  refreshRef.current = () => {
    void fetchData();
  };

  // Keep scanner history in sync with the shared bar (owned by AppShell bridge).
  useEffect(() => {
    if (!bar) return;
    if (bar.historyDate === historyDate) return;
    setHistoryDate(bar.historyDate);
    if (bar.historyDate === null) void fetchData();
  }, [bar, historyDate, setHistoryDate, fetchData]);

  useEffect(() => {
    const showFresh =
      tabUsesScannerPricePatch(activeTab) &&
      settings.discoveryProvider === 'ibkr' &&
      historyDate === null;
    const lastScan = scanAgeForTab(activeTab, scanAges);
    const ts = lastPriceTs > 0 ? lastPriceTs : lastScan;
    const secondsAgo =
      showFresh && ts > 0 ? Math.max(0, Math.floor(now - ts)) : null;

    patchScannerBarProps({
      secondsAgo,
      pricesStale: showFresh && pricesStale,
      onBackendStarted: () => refreshRef.current(),
    });
  }, [
    activeTab,
    historyDate,
    lastPriceTs,
    pricesStale,
    scanAges,
    now,
    settings.discoveryProvider,
  ]);

  return null;
}
