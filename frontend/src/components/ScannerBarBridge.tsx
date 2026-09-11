/**
 * Scanner-only patches for the shared GlobalAppBar status strip:
 * price freshness + backend-restart refresh. Never clears the bar on unmount.
 */
import { useEffect, useRef } from 'react';
import { useScannerData } from '../hooks/useScannerData';
import { scannerHonestyChip } from '../scanner/scannerHonesty';
import { useSettings } from '../settings/SettingsContext';
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
    setHistoryDate,
    subscriptionError,
    feedError,
    lastGood,
    tableMeta,
    catalystsError,
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
    const onLiveIbkr =
      settings.discoveryProvider === 'ibkr' && historyDate === null;
    const showFresh = onLiveIbkr && tabUsesScannerPricePatch(activeTab);
    const secondsAgo =
      showFresh && lastPriceTs > 0
        ? Math.max(0, Math.floor(now - lastPriceTs))
        : null;
    const honestyText = onLiveIbkr
      ? scannerHonestyChip({
          subscriptionError,
          feedError: feedError ?? (activeTab === 'catalysts' ? catalystsError : null),
          tableState: tableMeta[activeTab]?.state,
          lastGood: Boolean(lastGood[activeTab]),
        })
      : null;

    patchScannerBarProps({
      secondsAgo,
      lastPriceTs: showFresh ? lastPriceTs : null,
      pricesStale: showFresh && pricesStale,
      honestyText,
      onBackendStarted: () => refreshRef.current(),
    });
  }, [
    activeTab,
    historyDate,
    lastPriceTs,
    pricesStale,
    now,
    settings.discoveryProvider,
    subscriptionError,
    feedError,
    lastGood,
    tableMeta,
    catalystsError,
  ]);

  return null;
}
