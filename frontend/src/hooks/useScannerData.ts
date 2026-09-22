/**
 * Live + history scanner data (gappers / movers / AH / large cap / catalysts)
 * and IBKR price stream. Extracted from App.tsx.
 *
 * Every row passes the shape gate in scanner/scannerRowShape before it is
 * stored (QA C5 / C8); every REST reply is read through
 * scanner/scannerRest so a failed route is named on the board and retried
 * (QA C31), and persistent-authoritative desks keep their envelope fresh
 * (QA C48).
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
import { SCANNER_REST_RETRY_BASE_MS, SCANNER_REST_RETRY_MAX_MS } from '../constantGroups/scanner_board';
import { isNovaApiDebug } from '../debug';
import type { MarketMode } from '../types/market';
import type { Afterhours, Gapper, Mover, ScannerRow } from '../types/scanner';
import type { Catalyst } from '../types/catalyst';
import type { HealthStatus } from '../types/health';
import {
  useScannerPriceStream,
  type ScannerPricePatchRow,
  type ScannerTableMeta,
} from './useScannerPriceStream';
import type { ScannerScanAges } from '../utils/scanAge';
import { diagnoseBackend, healthAfterFailedRoute, logBackendDiagnosis } from '../utils/diagnoseBackend';
import {
  applyRosterTable,
  feedErrorFromPayload,
  SCANNER_CATALYSTS_FETCH_FAILED,
} from '../scanner/scannerHonesty';
import { fetchScannerHistory, type HistoryTableKey } from '../scanner/scannerHistory';
import {
  nextRetryDelay,
  SCANNER_ENVELOPE_TABLE_AGE,
  scannerRestErrorText,
  scannerRestTransportError,
} from '../scanner/scannerRest';
import {
  applyEnvelopeTables,
  applyScannerTableReplies,
  readCatalystReply,
  type ScannerRestSink,
} from '../scanner/scannerRestApply';
import {
  applyHonestPricePatch,
  normalizePatchRows,
  normalizeScannerRows,
} from '../scanner/scannerRowShape';
import { useScannerEnvelopePoll } from '../scanner/useScannerEnvelopePoll';

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
  /** A scanner REST route failed (HTTP, unreadable body, no answer) -- QA C31. */
  const [restError, setRestError] = useState<string | null>(null);
  const [catalystsError, setCatalystsError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  /** History view: tables whose snapshot request failed (cleared, not live) -- QA C51. */
  const [historyFailed, setHistoryFailed] = useState<HistoryTableKey[]>([]);
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
  /** True once every scanner route answered: only then does the failure grace apply. */
  const loadedOnceRef = useRef(false);
  const healthRef = useRef(health);
  healthRef.current = health;
  const historyDateRef = useRef(historyDate);
  historyDateRef.current = historyDate;
  const pollingRef = useRef(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryAttemptRef = useRef(0);
  const fetchDataRef = useRef<() => Promise<void>>(async () => {});

  const onScannerPricePatch = useCallback(
    (raw: ScannerPricePatchRow[], ts: number, table?: string | null) => {
      // QA C5: the patch is applied inside a state updater, outside the
      // socket's try/catch -- a row without a symbol must never get there.
      const rows = normalizePatchRows(raw);
      if (rows.length === 0) return;
      const apply = (setter: typeof setGappers, ageKey: keyof ScannerScanAges) => {
        setter(prev => applyHonestPricePatch(prev, rows));
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
        setGappers(prev => applyHonestPricePatch(prev, rows));
        setGainers(prev => applyHonestPricePatch(prev, rows));
        setLosers(prev => applyHonestPricePatch(prev, rows));
        setAfterhours(prev => applyHonestPricePatch(prev, rows));
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
    const ageKey = SCANNER_ENVELOPE_TABLE_AGE[table];
    if (ageKey) setScanAges(prev => ({ ...prev, [ageKey]: ts }));
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

  /** mode / health / data feed / feed_error, from any scanner envelope. */
  const applyEnvelope = useCallback((data: Record<string, unknown>) => {
    const nextHealth = data.health;
    if (nextHealth && typeof nextHealth === 'object' && !Array.isArray(nextHealth)) {
      setHealth(nextHealth as HealthStatus);
      const fellBack = (nextHealth as { feed_fell_back?: unknown }).feed_fell_back;
      if (typeof fellBack === 'boolean') onFeedFellBack?.(fellBack);
    }
    if (typeof data.mode === 'string' && data.mode) setMode(data.mode as Mode);
    if (typeof data.data_feed === 'string' && data.data_feed) onActiveFeed?.(data.data_feed);
    const feed = feedErrorFromPayload(data);
    if (feed !== undefined) setFeedError(feed);
  }, [onActiveFeed, onFeedFellBack]);

  const sinkRef = useRef<ScannerRestSink>(null as unknown as ScannerRestSink);
  sinkRef.current = {
    applyEnvelope,
    setGappers,
    setGainers,
    setLosers,
    setAfterhours,
    setLargeCap,
    setLastGood,
    setTableMeta,
    setScanAges,
  };

  const scheduleRetry = useCallback(() => {
    // A polling desk re-fetches on its own cadence; only the mount-once desk needs this.
    if (pollingRef.current || retryTimerRef.current != null) return;
    const delay = nextRetryDelay(retryAttemptRef.current, SCANNER_REST_RETRY_BASE_MS, SCANNER_REST_RETRY_MAX_MS);
    retryAttemptRef.current += 1;
    retryTimerRef.current = setTimeout(() => {
      retryTimerRef.current = null;
      if (historyDateRef.current === null) void fetchDataRef.current();
    }, delay);
  }, []);

  const fetchData = useCallback(async () => {
    const signal = AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS);
    let responses: Response[];
    try {
      responses = await Promise.all([
        fetch(`${API_URL}/gappers`, { signal }),
        fetch(`${API_URL}/movers`, { signal }),
        fetch(`${API_URL}/afterhours`, { signal }),
        fetch(`${API_URL}/large-cap`, { signal }),
        fetch(`${API_URL}/news-catalysts`, { signal }),
      ]);
    } catch (e) {
      consecutiveFailuresRef.current += 1;
      scheduleRetry();
      // The grace keeps a board that has rows from flapping on a blip. Before
      // anything has loaded there is nothing to protect: "Loading market
      // data…" over an API that never answers is a failure unstated (QA D10).
      if (loadedOnceRef.current && consecutiveFailuresRef.current < SCANNER_HEALTH_FAIL_GRACE_COUNT) {
        console.warn('[Nova] Scanner REST fetch failed; retrying', e);
        return;
      }
      setRestError(scannerRestTransportError(e));
      const diag = await diagnoseBackend();
      logBackendDiagnosis(diag);
      if (diag.ok) {
        console.warn('[Nova] Scanner API route failed; /api/health is OK', {
          API_URL,
          flag: diag.flag,
          health_url: `${API_BASE_URL}/api/health`,
        });
      } else {
        console.error('[Nova] Scanner API network error', {
          API_URL,
          API_BASE_URL,
          flag: diag.flag,
          hint: diag.hint,
          health_url: `${API_BASE_URL}/api/health`,
          trace: isNovaApiDebug() ? e : '(set localStorage novaApiDebug=1 and reload for details)',
        });
      }
      setHealth(healthAfterFailedRoute(healthRef.current, diag));
      return;
    }
    // A late answer must not paint live rows over a history view (QA C51).
    if (historyDateRef.current !== null) return;
    const [gr, moversRes, ahRes, largeCapRes, catalystRes] = responses;
    const failures = await applyScannerTableReplies(
      { gappers: gr, movers: moversRes, afterhours: ahRes, largeCap: largeCapRes },
      sinkRef.current,
    );
    const cat = await readCatalystReply(catalystRes);
    if (cat.rows) setCatalysts(cat.rows);
    setCatalystsError(cat.error);

    const errText = scannerRestErrorText(failures);
    setRestError(errText);
    if (errText) {
      console.warn(`[Nova] ${errText}`);
      scheduleRetry();
    } else {
      consecutiveFailuresRef.current = 0;
      retryAttemptRef.current = 0;
      loadedOnceRef.current = true;
    }
  }, [scheduleRetry]);
  fetchDataRef.current = fetchData;

  const fetchCatalystsOnly = useCallback(async () => {
    try {
      const cat = await readCatalystReply(await fetch(`${API_URL}/news-catalysts`, {
        signal: AbortSignal.timeout(SCANNER_FETCH_TIMEOUT_MS),
      }));
      if (cat.rows) setCatalysts(cat.rows);
      setCatalystsError(cat.error);
    } catch {
      setCatalystsError(SCANNER_CATALYSTS_FETCH_FAILED);
    }
  }, []);

  const fetchHistoryDates = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/history/dates?type=gappers`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data?.dates)) setHistoryDates(data.dates.filter((d: unknown) => typeof d === 'string'));
      }
    } catch (err) {
      console.warn('[Nova] Scanner history dates did not load', err);
    }
  }, []);

  const fetchHistoryData = useCallback(async (date: string) => {
    const { tables, error, failed } = await fetchScannerHistory(API_URL, date);
    if (historyDateRef.current !== date) return;
    // Every table is replaced -- a failed one is cleared and named (QA C51).
    setGappers(normalizeScannerRows(tables.gappers) ?? []);
    setGainers(normalizeScannerRows(tables.gainers) ?? []);
    setLosers(normalizeScannerRows(tables.losers) ?? []);
    setAfterhours(normalizeScannerRows(tables.afterhours) ?? []);
    setLargeCap(normalizeScannerRows(tables.largeCap) ?? []);
    setHistoryError(error);
    setHistoryFailed(failed);
  }, []);

  useEffect(() => {
    if (historyDate !== null) return;
    setHistoryError(null);
    setHistoryFailed([]);
    fetchData();
    const ibkr = discoveryProvider === 'ibkr';
    // ADR 008 cutover: when persistent scanner is authoritative, drop recurring
    // structural REST polls — roster_replace / table_state own membership.
    const pollMs = !ibkr
      ? SCANNER_POLL_INTERVAL_MS
      : scannerPersistentAuthoritative
        ? null
        : SCANNER_POLL_INTERVAL_IBKR_MS;
    pollingRef.current = pollMs != null;
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
      if (retryTimerRef.current != null) clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    };
  }, [
    fetchData,
    fetchCatalystsOnly,
    historyDate,
    discoveryProvider,
    scannerPersistentAuthoritative,
  ]);

  const onEnvelope = useCallback((data: Record<string, unknown>) => {
    applyEnvelope(data);
    applyEnvelopeTables(data, sinkRef.current);
  }, [applyEnvelope]);

  useScannerEnvelopePoll({
    enabled: discoveryProvider === 'ibkr' && scannerPersistentAuthoritative && historyDate === null,
    onEnvelope,
  });

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
    restError,
    catalystsError,
    historyError,
    historyFailed,
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
