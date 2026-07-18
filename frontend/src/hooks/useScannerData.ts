/**
 * Live + history scanner data (gappers / movers / AH / catalysts) and IBKR price stream.
 * Extracted from App.tsx.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE_URL,
  API_URL,
  SCANNER_FETCH_TIMEOUT_MS,
  SCANNER_POLL_INTERVAL_IBKR_MS,
  SCANNER_POLL_INTERVAL_MS,
} from '../constants';
import { isNovaApiDebug } from '../debug';
import type { MarketMode } from '../components/AppHeader';
import type { Afterhours, Gapper, Mover } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import {
  applyScannerPricePatch,
  useScannerPriceStream,
} from './useScannerPriceStream';
import type { ScannerScanAges } from '../utils/scanAge';
import { diagnoseBackend, logBackendDiagnosis } from '../utils/diagnoseBackend';

type Mode = MarketMode;

export function useScannerData(opts: {
  discoveryProvider: string;
  /** Active UI tab — drives IBKR L1 subscription budget via /ws/scanner. */
  activeTab?: string;
  onActiveFeed?: (feed: string) => void;
  onFeedFellBack?: (fellBack: boolean) => void;
}) {
  const { discoveryProvider, activeTab, onActiveFeed, onFeedFellBack } = opts;

  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [gainers, setGainers] = useState<Mover[]>([]);
  const [losers, setLosers] = useState<Mover[]>([]);
  const [afterhours, setAfterhours] = useState<Afterhours[]>([]);
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);
  const [scanAges, setScanAges] = useState<ScannerScanAges>({
    gappers: 0,
    movers: 0,
    afterhours: 0,
  });
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [historyDate, setHistoryDate] = useState<string | null>(null);
  const [historyDates, setHistoryDates] = useState<string[]>([]);

  const onScannerPricePatch = useCallback(
    (rows: Parameters<typeof applyScannerPricePatch>[1], ts: number) => {
      setGappers(prev => applyScannerPricePatch(prev, rows));
      setGainers(prev => applyScannerPricePatch(prev, rows));
      setLosers(prev => applyScannerPricePatch(prev, rows));
      setAfterhours(prev => applyScannerPricePatch(prev, rows));
      setScanAges(prev => ({
        ...prev,
        gappers: Math.max(prev.gappers, ts),
        movers: Math.max(prev.movers, ts),
        afterhours: Math.max(prev.afterhours, ts),
      }));
    },
    [],
  );

  const { pricesStale, flashSymbols, lastPriceTs, rowQuoteTs, subscriptionError } =
    useScannerPriceStream({
      enabled: discoveryProvider === 'ibkr' && historyDate === null,
      activeTab,
      onPatch: onScannerPricePatch,
    });

  const fetchData = useCallback(async () => {
    const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
    try {
      const [gr, moversRes, ahRes, catalystRes] = await Promise.all([
        fetch(`${API_URL}/gappers`, { signal }),
        fetch(`${API_URL}/movers`, { signal }),
        fetch(`${API_URL}/afterhours`, { signal }),
        fetch(`${API_URL}/news-catalysts`, { signal }),
      ]);

      let nextAges: Partial<ScannerScanAges> = {};

      if (gr.ok) {
        const data = await gr.json();
        if (data.health) {
          setHealth(data.health);
          if (data.health.feed_fell_back != null) onFeedFellBack?.(data.health.feed_fell_back);
        }
        if (data.mode) setMode(data.mode as Mode);
        if (data.data_feed) onActiveFeed?.(data.data_feed);
        if (Array.isArray(data.gappers)) setGappers(data.gappers);
        if (data.last_scan) nextAges = { ...nextAges, gappers: data.last_scan };
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, movers: data.last_scan };
        if (Array.isArray(data.gainers)) setGainers(data.gainers);
        if (Array.isArray(data.losers)) setLosers(data.losers);
      }

      if (ahRes.ok) {
        const data = await ahRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, afterhours: data.last_scan };
        if (Array.isArray(data.afterhours)) setAfterhours(data.afterhours);
      }

      if (Object.keys(nextAges).length > 0) {
        setScanAges(prev => ({ ...prev, ...nextAges }));
      }

      if (catalystRes.ok) {
        const data = await catalystRes.json();
        if (Array.isArray(data.catalysts)) setCatalysts(data.catalysts);
      }

      if (isNovaApiDebug()) {
        for (const [label, res] of [
          ['gappers', gr],
          ['movers', moversRes],
          ['afterhours', ahRes],
          ['catalysts', catalystRes],
        ] as const) {
          if (!res.ok) {
            console.warn(`[Nova] GET ${API_URL}/${label} -> HTTP ${res.status}`, res.statusText);
          }
        }
      }
    } catch (e) {
      const diag = await diagnoseBackend();
      logBackendDiagnosis(diag);
      console.error('[Nova] Scanner API network error', {
        API_URL,
        API_BASE_URL,
        flag: diag.flag,
        hint: diag.hint,
        health_url: `${API_BASE_URL}/api/health`,
        trace: isNovaApiDebug() ? e : '(set localStorage novaApiDebug=1 and reload for details)',
      });
      if (isNovaApiDebug()) {
        console.info(
          '[Nova] F12 → Network: find failed request to /api/gappers. Console: localStorage.setItem("novaApiDebug","1") then reload.',
        );
      }
      setHealth({
        status: 'disconnected',
        latency_ms: 0,
        message: diag.message,
        flag: diag.flag,
        flag_hint: diag.hint,
      });
    }
  }, [onActiveFeed, onFeedFellBack]);

  const fetchHistoryDates = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/history/dates?type=gappers`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.dates)) setHistoryDates(data.dates);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchHistoryData = useCallback(async (date: string) => {
    try {
      const [gr, moversRes, ahRes] = await Promise.all([
        fetch(`${API_URL}/history/gappers/${date}`),
        fetch(`${API_URL}/history/movers/${date}`),
        fetch(`${API_URL}/history/afterhours/${date}`),
      ]);
      if (gr.ok) {
        const data = await gr.json();
        setGappers(Array.isArray(data.gappers) ? data.gappers : []);
      }
      if (moversRes.ok) {
        const data = await moversRes.json();
        setGainers(Array.isArray(data.gainers) ? data.gainers : []);
        setLosers(Array.isArray(data.losers) ? data.losers : []);
      }
      if (ahRes.ok) {
        const data = await ahRes.json();
        setAfterhours(Array.isArray(data.afterhours) ? data.afterhours : []);
      }
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    if (historyDate !== null) return;
    fetchData();
    // IBKR: /ws/scanner already streams live price patches — this REST poll only
    // needs to catch structural changes, so it can run much slower than 1Hz.
    const pollMs =
      discoveryProvider === 'ibkr' ? SCANNER_POLL_INTERVAL_IBKR_MS : SCANNER_POLL_INTERVAL_MS;
    const dataInterval = setInterval(fetchData, pollMs);
    const clockInterval = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      clearInterval(dataInterval);
      clearInterval(clockInterval);
    };
  }, [fetchData, historyDate, discoveryProvider]);

  useEffect(() => {
    fetchHistoryDates();
  }, [fetchHistoryDates]);

  useEffect(() => {
    if (historyDate) fetchHistoryData(historyDate);
  }, [historyDate, fetchHistoryData]);

  return {
    mode,
    health,
    gappers,
    gainers,
    losers,
    afterhours,
    catalysts,
    scanAges,
    now,
    historyDate,
    setHistoryDate,
    historyDates,
    pricesStale,
    flashSymbols,
    lastPriceTs,
    rowQuoteTs,
    subscriptionError,
    fetchData,
  };
}
