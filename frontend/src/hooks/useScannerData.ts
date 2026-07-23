/**
 * Live + history scanner data (gappers / movers / AH / catalysts) and IBKR price stream.
 * Extracted from App.tsx.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  API_BASE_URL,
  API_URL,
  SCANNER_CATALYST_POLL_MS,
  SCANNER_FETCH_TIMEOUT_MS,
  SCANNER_HEALTH_FAIL_GRACE_COUNT,
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
  type ScannerTableMeta,
} from './useScannerPriceStream';
import type { ScannerScanAges } from '../utils/scanAge';
import { diagnoseBackend, logBackendDiagnosis } from '../utils/diagnoseBackend';

type Mode = MarketMode;

function setTableRows<T>(
  setter: (fn: (prev: T[]) => T[]) => void,
  rows: unknown,
): void {
  if (!Array.isArray(rows)) return;
  setter(prev => (rows.length === 0 && prev.length > 0 ? prev : (rows as T[])));
}

export function useScannerData(opts: {
  discoveryProvider: string;
  /** Active UI tab — drives IBKR L1 subscription budget via /ws/scanner. */
  activeTab?: string;
  /** When true, skip recurring IBKR membership REST polls (ADR 008 cutover). */
  scannerPersistentAuthoritative?: boolean;
  onActiveFeed?: (feed: string) => void;
  onFeedFellBack?: (fellBack: boolean) => void;
}) {
  const {
    discoveryProvider,
    activeTab,
    scannerPersistentAuthoritative = false,
    onActiveFeed,
    onFeedFellBack,
  } = opts;

  const [mode, setMode] = useState<Mode>('loading');
  const [health, setHealth] = useState<HealthStatus>({ status: 'loading', latency_ms: 0 });
  const [gappers, setGappers] = useState<Gapper[]>([]);
  const [gainers, setGainers] = useState<Mover[]>([]);
  const [losers, setLosers] = useState<Mover[]>([]);
  const [afterhours, setAfterhours] = useState<Afterhours[]>([]);
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);
  const [tableMeta, setTableMeta] = useState<Record<string, ScannerTableMeta>>({});
  const [scanAges, setScanAges] = useState<ScannerScanAges>({
    gappers: 0,
    movers: 0,
    afterhours: 0,
  });
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [historyDate, setHistoryDate] = useState<string | null>(null);
  const [historyDates, setHistoryDates] = useState<string[]>([]);
  const consecutiveFailuresRef = useRef(0);

  const onScannerPricePatch = useCallback(
    (rows: Parameters<typeof applyScannerPricePatch>[1], ts: number, table?: string | null) => {
      const apply = (setter: typeof setGappers, ageKey: keyof ScannerScanAges) => {
        setter(prev => applyScannerPricePatch(prev, rows) as typeof prev);
        setScanAges(prev => ({ ...prev, [ageKey]: Math.max(prev[ageKey], ts) }));
      };
      // Table-scoped: never let a live Gainers tick mutate a frozen Gappers row.
      if (table === 'gappers') apply(setGappers, 'gappers');
      else if (table === 'gainers') apply(setGainers, 'movers');
      else if (table === 'losers') apply(setLosers, 'movers');
      else if (table === 'afterhours') apply(setAfterhours, 'afterhours');
      else {
        // Legacy patches without table — apply to all (shadow / older backends).
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
      }
    },
    [],
  );

  const onRosterReplace = useCallback((table: string, rows: unknown[], meta: ScannerTableMeta) => {
    setTableMeta(prev => ({ ...prev, [table]: meta }));
    if (table === 'gappers') setTableRows(setGappers, rows);
    else if (table === 'gainers') setTableRows(setGainers, rows);
    else if (table === 'losers') setTableRows(setLosers, rows);
    else if (table === 'afterhours') setTableRows(setAfterhours, rows);
    const ts = meta.roster_ts || Date.now() / 1000;
    if (table === 'gappers') setScanAges(prev => ({ ...prev, gappers: ts }));
    else if (table === 'gainers' || table === 'losers') {
      setScanAges(prev => ({ ...prev, movers: ts }));
    } else if (table === 'afterhours') {
      setScanAges(prev => ({ ...prev, afterhours: ts }));
    }
  }, []);

  const onTableState = useCallback((table: string, meta: ScannerTableMeta) => {
    setTableMeta(prev => ({ ...prev, [table]: meta }));
  }, []);

  const { pricesStale, flashSymbols, lastPriceTs, rowQuoteTs, subscriptionError } =
    useScannerPriceStream({
      enabled: discoveryProvider === 'ibkr' && historyDate === null,
      activeTab,
      onPatch: onScannerPricePatch,
      onRosterReplace,
      onTableState,
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
      consecutiveFailuresRef.current = 0;

      let nextAges: Partial<ScannerScanAges> = {};

      if (gr.ok) {
        const data = await gr.json();
        if (data.health) {
          setHealth(data.health);
          if (data.health.feed_fell_back != null) onFeedFellBack?.(data.health.feed_fell_back);
        }
        if (data.mode) setMode(data.mode as Mode);
        if (data.data_feed) onActiveFeed?.(data.data_feed);
        if (Array.isArray(data.gappers)) {
          setGappers(prev =>
            data.gappers.length === 0 && prev.length > 0 ? prev : data.gappers,
          );
        }
        if (data.last_scan) nextAges = { ...nextAges, gappers: data.last_scan };
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, movers: data.last_scan };
        if (Array.isArray(data.gainers)) {
          setGainers(prev =>
            data.gainers.length === 0 && prev.length > 0 ? prev : data.gainers,
          );
        }
        if (Array.isArray(data.losers)) {
          setLosers(prev =>
            data.losers.length === 0 && prev.length > 0 ? prev : data.losers,
          );
        }
      }

      if (ahRes.ok) {
        const data = await ahRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, afterhours: data.last_scan };
        if (Array.isArray(data.afterhours)) {
          setAfterhours(prev =>
            data.afterhours.length === 0 && prev.length > 0 ? prev : data.afterhours,
          );
        }
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
      consecutiveFailuresRef.current += 1;
      if (consecutiveFailuresRef.current < SCANNER_HEALTH_FAIL_GRACE_COUNT) {
        return;
      }
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
      setHealth({
        status: 'disconnected',
        latency_ms: 0,
        message: diag.message,
        flag: diag.flag,
        flag_hint: diag.hint,
      });
    }
  }, [onActiveFeed, onFeedFellBack]);

  const fetchCatalystsOnly = useCallback(async () => {
    try {
      const catalystRes = await fetch(`${API_URL}/news-catalysts`, {
        signal: AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS),
      });
      if (catalystRes.ok) {
        const data = await catalystRes.json();
        if (Array.isArray(data.catalysts)) setCatalysts(data.catalysts);
      }
    } catch {
      // soft — membership comes from WS when authoritative
    }
  }, []);

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
    const ibkr = discoveryProvider === 'ibkr';
    // ADR 008 cutover: when persistent scanner is authoritative, drop recurring
    // structural REST polls — roster_replace / table_state own membership.
    const pollMs = !ibkr
      ? SCANNER_POLL_INTERVAL_MS
      : scannerPersistentAuthoritative
        ? null
        : SCANNER_POLL_INTERVAL_IBKR_MS;
    const dataInterval =
      pollMs != null ? setInterval(fetchData, pollMs) : null;
    const catalystInterval =
      ibkr && scannerPersistentAuthoritative
        ? setInterval(fetchCatalystsOnly, SCANNER_CATALYST_POLL_MS)
        : null;
    const clockInterval = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => {
      if (dataInterval) clearInterval(dataInterval);
      if (catalystInterval) clearInterval(catalystInterval);
      clearInterval(clockInterval);
    };
  }, [
    fetchData,
    fetchCatalystsOnly,
    historyDate,
    discoveryProvider,
    scannerPersistentAuthoritative,
  ]);

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
    tableMeta,
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
