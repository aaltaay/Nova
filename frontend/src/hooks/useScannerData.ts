/**
 * Live + history scanner data (gappers / movers / AH / large cap / catalysts)
 * and IBKR price stream. Extracted from App.tsx.
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
import type { Afterhours, Gapper, Mover, ScannerRow } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import {
  applyScannerPricePatch,
  useScannerPriceStream,
  type ScannerTableMeta,
} from './useScannerPriceStream';
import type { ScannerScanAges } from '../utils/scanAge';
import { diagnoseBackend, logBackendDiagnosis } from '../utils/diagnoseBackend';
import {
  applyRosterTable,
  catalystsHttpError,
  feedErrorFromPayload,
  mergeRestTableMeta,
  SCANNER_CATALYSTS_FETCH_FAILED,
} from '../scanner/scannerHonesty';
import { fetchScannerHistory } from '../scanner/scannerHistory';

type Mode = MarketMode;

export function useScannerData(opts: {
  discoveryProvider: string;
  /** Every scanner table on screen — drives IBKR L1 budget via /ws/scanner. */
  activeTabs?: readonly string[];
  /** When true, skip recurring IBKR membership REST polls (ADR 008 cutover). */
  scannerPersistentAuthoritative?: boolean;
  onActiveFeed?: (feed: string) => void;
  onFeedFellBack?: (fellBack: boolean) => void;
}) {
  const {
    discoveryProvider,
    activeTabs,
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
  const [largeCap, setLargeCap] = useState<ScannerRow[]>([]);
  const [catalysts, setCatalysts] = useState<Catalyst[]>([]);
  const [tableMeta, setTableMeta] = useState<Record<string, ScannerTableMeta>>({});
  const [lastGood, setLastGood] = useState<Record<string, boolean>>({});
  const [feedError, setFeedError] = useState<string | null>(null);
  const [catalystsError, setCatalystsError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [scanAges, setScanAges] = useState<ScannerScanAges>({
    gappers: 0,
    movers: 0,
    afterhours: 0,
    largeCap: 0,
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
      else if (table === 'large_cap') apply(setLargeCap, 'largeCap');
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
    if (table === 'gappers') applyRosterTable(setGappers, setLastGood, table, rows);
    else if (table === 'gainers') applyRosterTable(setGainers, setLastGood, table, rows);
    else if (table === 'losers') applyRosterTable(setLosers, setLastGood, table, rows);
    else if (table === 'afterhours') applyRosterTable(setAfterhours, setLastGood, table, rows);
    else if (table === 'large_cap') applyRosterTable(setLargeCap, setLastGood, table, rows);
    const ts = meta.roster_ts || Date.now() / 1000;
    if (table === 'gappers') setScanAges(prev => ({ ...prev, gappers: ts }));
    else if (table === 'gainers' || table === 'losers') {
      setScanAges(prev => ({ ...prev, movers: ts }));
    } else if (table === 'afterhours') {
      setScanAges(prev => ({ ...prev, afterhours: ts }));
    } else if (table === 'large_cap') {
      setScanAges(prev => ({ ...prev, largeCap: ts }));
    }
  }, []);

  const onTableState = useCallback((table: string, meta: ScannerTableMeta) => {
    setTableMeta(prev => ({ ...prev, [table]: meta }));
  }, []);

  const { pricesStale, flashSymbols, lastPriceTs, rowQuoteTs, subscriptionError } =
    useScannerPriceStream({
      enabled: discoveryProvider === 'ibkr' && historyDate === null,
      activeTabs,
      onPatch: onScannerPricePatch,
      onRosterReplace,
      onTableState,
    });

  const fetchData = useCallback(async () => {
    const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
    try {
      const [gr, moversRes, ahRes, largeCapRes, catalystRes] = await Promise.all([
        fetch(`${API_URL}/gappers`, { signal }),
        fetch(`${API_URL}/movers`, { signal }),
        fetch(`${API_URL}/afterhours`, { signal }),
        fetch(`${API_URL}/large-cap`, { signal }),
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
        applyRosterTable(setGappers, setLastGood, 'gappers', data.gappers);
        setTableMeta(prev => mergeRestTableMeta(prev, 'gappers', data.table_state, data.roster_ts));
        const gapFeed = feedErrorFromPayload(data);
        if (gapFeed !== undefined) setFeedError(gapFeed);
        if (data.last_scan) nextAges = { ...nextAges, gappers: data.last_scan };
      }

      if (moversRes.ok) {
        const data = await moversRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, movers: data.last_scan };
        applyRosterTable(setGainers, setLastGood, 'gainers', data.gainers);
        applyRosterTable(setLosers, setLastGood, 'losers', data.losers);
        setTableMeta(prev => {
          let next = mergeRestTableMeta(prev, 'gainers', data.table_state, data.roster_ts);
          next = mergeRestTableMeta(next, 'losers', data.loser_table_state, data.loser_roster_ts);
          return next;
        });
        const moversFeed = feedErrorFromPayload(data);
        if (moversFeed !== undefined) setFeedError(moversFeed);
      }

      if (ahRes.ok) {
        const data = await ahRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, afterhours: data.last_scan };
        applyRosterTable(setAfterhours, setLastGood, 'afterhours', data.afterhours);
        setTableMeta(prev => mergeRestTableMeta(prev, 'afterhours', data.table_state, data.roster_ts));
        const ahFeed = feedErrorFromPayload(data);
        if (ahFeed !== undefined) setFeedError(ahFeed);
      }

      if (largeCapRes.ok) {
        const data = await largeCapRes.json();
        if (data.mode) setMode(data.mode as Mode);
        if (data.last_scan) nextAges = { ...nextAges, largeCap: data.last_scan };
        applyRosterTable(setLargeCap, setLastGood, 'large_cap', data.large_cap);
        setTableMeta(prev => mergeRestTableMeta(prev, 'large_cap', data.table_state, data.roster_ts));
        const lcFeed = feedErrorFromPayload(data);
        if (lcFeed !== undefined) setFeedError(lcFeed);
      }

      if (Object.keys(nextAges).length > 0) {
        setScanAges(prev => ({ ...prev, ...nextAges }));
      }

      if (catalystRes.ok) {
        const data = await catalystRes.json();
        if (Array.isArray(data.catalysts)) {
          setCatalysts(data.catalysts);
          setCatalystsError(null);
        }
      } else {
        setCatalystsError(catalystsHttpError(catalystRes.status));
      }

      if (isNovaApiDebug()) {
        for (const [label, res] of [
          ['gappers', gr],
          ['movers', moversRes],
          ['afterhours', ahRes],
          ['large-cap', largeCapRes],
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
        if (Array.isArray(data.catalysts)) {
          setCatalysts(data.catalysts);
          setCatalystsError(null);
        }
      } else {
        setCatalystsError(catalystsHttpError(catalystRes.status));
      }
    } catch {
      setCatalystsError(SCANNER_CATALYSTS_FETCH_FAILED);
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
    const { tables, error } = await fetchScannerHistory(API_URL, date);
    setLargeCap(tables.largeCap as ScannerRow[]);
    if (error) {
      setHistoryError(error);
      return;
    }
    setHistoryError(null);
    if (tables.gappers) setGappers(tables.gappers as Gapper[]);
    if (tables.gainers) setGainers(tables.gainers as Mover[]);
    if (tables.losers) setLosers(tables.losers as Mover[]);
    if (tables.afterhours) setAfterhours(tables.afterhours as Afterhours[]);
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
    largeCap,
    catalysts,
    tableMeta,
    lastGood,
    feedError,
    catalystsError,
    historyError,
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
