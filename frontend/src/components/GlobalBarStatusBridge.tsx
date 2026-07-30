/**
 * Always-on publisher for the GlobalAppBar middle status strip.
 * Mounted in AppShell so Scanner and Trader share one header (no clear on route change).
 */
import { useEffect, useState, type ChangeEvent } from 'react';
import { API_URL, SCANNER_POLL_INTERVAL_IBKR_MS } from '../constants';
import { enterSampleView } from '../sample_data/sampleNav';
import { useSettings } from '../settings/SettingsContext';
import type { HealthStatus } from '../types/health';
import { useWorkspace } from '../workspace/WorkspaceContext';
import type { GlobalAppBarScanner } from './globalAppBarScanner';
import {
  publishGlobalBarCore,
  setGlobalBarHistoryDate,
  setGlobalBarHistoryDates,
  useScannerBarProps,
} from './scannerBarStore';

const EMPTY_HEALTH: HealthStatus = { status: 'loading', latency_ms: 0 };

export function GlobalBarStatusBridge() {
  const { settings } = useSettings();
  const { ibkrConnected, ibkrMode, ibkrGatewayMode, setSelectedSymbol } = useWorkspace();
  const bar = useScannerBarProps();
  const [mode, setMode] = useState<GlobalAppBarScanner['mode']>('loading');
  const [health, setHealth] = useState<HealthStatus>(EMPTY_HEALTH);
  const historyDate = bar?.historyDate ?? null;
  const historyDates = bar?.historyDates ?? [];

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${API_URL}/mode`, {
          signal: AbortSignal.timeout(4000),
        });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          mode?: GlobalAppBarScanner['mode'];
          health?: HealthStatus;
        };
        if (cancelled) return;
        if (data.mode) setMode(data.mode);
        if (data.health) setHealth(data.health);
      } catch {
        if (!cancelled) {
          setHealth({
            status: 'disconnected',
            latency_ms: 0,
            message: 'Backend hung (no health response)',
            flag: 'API_WEDGED',
          });
        }
      }
    };
    void poll();
    const id = window.setInterval(poll, SCANNER_POLL_INTERVAL_IBKR_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/history/dates?type=gappers`);
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { dates?: string[] };
        if (!cancelled && Array.isArray(data.dates)) {
          setGlobalBarHistoryDates(data.dates);
        }
      } catch {
        // soft -- history dropdown stays empty
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onHistoryChange = (e: ChangeEvent<HTMLSelectElement>) => {
      const val = e.target.value;
      setGlobalBarHistoryDate(val === '' ? null : val);
    };

    publishGlobalBarCore({
      mode,
      health,
      activeFeed: settings.activeFeed,
      feedFellBack: settings.feedFellBack,
      ibkrConnected,
      ibkrMode,
      ibkrGatewayMode,
      onHistoryChange,
      onLookup: setSelectedSymbol,
      showScannerSource: true,
      discoveryProvider: settings.discoveryProvider,
      sampleDataActive: false,
      onSampleDataToggle: (on: boolean) => {
        if (on) enterSampleView();
      },
    });
  }, [
    mode,
    health,
    settings.activeFeed,
    settings.feedFellBack,
    settings.discoveryProvider,
    ibkrConnected,
    ibkrMode,
    ibkrGatewayMode,
    historyDate,
    historyDates,
    setSelectedSymbol,
  ]);

  return null;
}
