/** WebSocket ticker detail stream — Phase 1 fast snapshot, Phase 2 slow enrich, live trades. */
import { useEffect, useRef, useState } from 'react';
import {
  API_BASE_URL,
  TICKER_WS_HTTP_SEED_MS,
  TICKER_WS_RECONNECT_CAP_MS,
  TICKER_WS_RECONNECT_MS,
  WS_BASE_URL,
} from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { BarData, TickerDetail, TickerTradeUpdate } from '../types/ticker';
import { applyBarsPatch, parseBarsCoverage } from '../chart/barsStore';
import { tickerDetailFromHttp, tickerDetailFromWsInitial } from './tickerStreamHttp';
import { countSocketMessage, frameBytes } from '../perf/perfCounters';

const WS_URL = `${WS_BASE_URL}/ws`;

export type TickerStreamState = {
  detail: TickerDetail | null;
  loading: boolean;
  refreshing: boolean;
  fetchFailed: boolean;
  stale: boolean;
  disconnectedSince: number | null;
};

const IDLE_STREAM: TickerStreamState = {
  detail: null,
  loading: false,
  refreshing: false,
  fetchFailed: false,
  stale: false,
  disconnectedSince: null,
};

export function useTickerStream(symbol: string | null): TickerStreamState {
  const sample = useSampleDataOptional();
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const [stale, setStale] = useState(false);
  const [disconnectedSince, setDisconnectedSince] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const hasDetailRef = useRef(false);
  const backoffRef = useRef(TICKER_WS_RECONNECT_MS);
  const mountedRef = useRef(true);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    if (sample) return;
    if (!symbol) {
      hasDetailRef.current = false;
      setDetail(null);
      setLoading(false);
      setRefreshing(false);
      setFetchFailed(false);
      setStale(false);
      setDisconnectedSince(null);
      return;
    }

    const symKey = symbol;
    let cancelled = false;
    let initialReceived = false;
    backoffRef.current = TICKER_WS_RECONNECT_MS;

    // Symbol gate: never keep the previous ticker's detail while the new one loads.
    hasDetailRef.current = false;
    setDetail(null);
    setFetchFailed(false);
    setStale(false);
    setDisconnectedSince(null);
    setLoading(true);
    setRefreshing(true);

    const seedCtl = new AbortController();
    const seedTimer = window.setTimeout(() => {
      if (cancelled || initialReceived || !mountedRef.current) return;
      void fetch(`${API_BASE_URL}/api/ticker/${encodeURIComponent(symKey)}`, {
        signal: seedCtl.signal,
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (cancelled || initialReceived || !mountedRef.current) return;
          const seeded = tickerDetailFromHttp(data, symKey);
          if (!seeded) return;
          initialReceived = true;
          hasDetailRef.current = true;
          setDetail(seeded);
          setLoading(false);
          setRefreshing(false);
          setFetchFailed(false);
          setStale(false);
          setDisconnectedSince(null);
        })
        .catch(() => {
          /* WS may still deliver initial */
        });
    }, TICKER_WS_HTTP_SEED_MS);

    function markLive() {
      setStale(false);
      setDisconnectedSince(null);
      setFetchFailed(false);
    }

    function connect() {
      if (!mountedRef.current || cancelled) return;
      const ws = new WebSocket(`${WS_URL}/ticker/${symKey}`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current || ws !== wsRef.current) return;
        backoffRef.current = TICKER_WS_RECONNECT_MS;
      };

      ws.onmessage = (e) => {
        countSocketMessage('ticker', frameBytes(e.data));
        if (cancelled || !mountedRef.current || ws !== wsRef.current) return;
        try {
          const msg = JSON.parse(e.data);
          const msgSym = typeof msg.symbol === 'string' ? msg.symbol.toUpperCase() : null;
          if (msgSym != null && msgSym !== symKey) return;

          if (msg.type === 'initial') {
            const next = tickerDetailFromWsInitial(msg, symKey);
            if (!next) {
              setLoading(false);
              setRefreshing(false);
              setFetchFailed(true);
              return;
            }
            initialReceived = true;
            hasDetailRef.current = true;
            setDetail(next);
            setLoading(false);
            setRefreshing(false);
            markLive();
          } else if (msg.type === 'detail_update') {
            if (!initialReceived) return;
            markLive();
            setDetail(prev => {
              if (!prev || prev.symbol.toUpperCase() !== symKey) return prev;
              return {
                ...prev,
                news: msg.news ?? prev.news,
                fundamentals: msg.fundamentals ?? prev.fundamentals,
                avg_volume: msg.avg_volume ?? prev.avg_volume,
                rel_volume: msg.rel_volume ?? prev.rel_volume,
                rvol_5min: msg.rvol_5min ?? prev.rvol_5min,
                volume_in_5min: msg.volume_in_5min ?? prev.volume_in_5min,
                news_impact: msg.news_impact ?? prev.news_impact,
                listing: msg.listing ?? prev.listing,
                halt: msg.halt !== undefined ? msg.halt : prev.halt,
              };
            });
          } else if (msg.type === 'halt_update') {
            if (!initialReceived) return;
            markLive();
            setDetail(prev => {
              if (!prev || prev.symbol.toUpperCase() !== symKey) return prev;
              return { ...prev, halt: msg.halt ?? null };
            });
          } else if (msg.type === 'bars_patch') {
            const tf = typeof msg.timeframe === 'string' ? msg.timeframe : '';
            if (!tf || !Array.isArray(msg.bars)) return;
            applyBarsPatch(symKey, tf, msg.bars, parseBarsCoverage(msg.coverage));
          } else if (msg.type === 'trade_update') {
            if (!initialReceived) return;
            markLive();
            const update = msg as TickerTradeUpdate;
            setDetail(prev => {
              if (!prev || prev.symbol.toUpperCase() !== symKey) return prev;
              const newPrice = update.price;
              const prevDailyBar = prev.snapshot?.daily_bar ?? null;
              const newDailyBar: BarData | null = prevDailyBar
                ? {
                    ...prevDailyBar,
                    close: newPrice,
                    volume: update.volume ?? prevDailyBar.volume,
                  }
                : {
                    open: null,
                    high: null,
                    low: null,
                    close: newPrice,
                    volume: update.volume ?? null,
                    trade_count: null,
                    vwap: null,
                    timestamp: null,
                  };
              const nextPrevClose = update.prev_close ?? prev.snapshot?.prev_close ?? null;
              const newSnapshot = {
                ...prev.snapshot,
                daily_bar: newDailyBar,
                prev_close: nextPrevClose,
                session_close: update.prev_close != null
                  ? update.prev_close
                  : prev.snapshot?.session_close ?? null,
                latest_trade: {
                  price: newPrice,
                  size: update.size ?? prev.snapshot?.latest_trade?.size ?? null,
                  timestamp: update.timestamp ?? prev.snapshot?.latest_trade?.timestamp ?? null,
                  exchange: prev.snapshot?.latest_trade?.exchange ?? null,
                  // Older backends send no source: treat as a print, as before.
                  source: update.source ?? 'stream',
                  day_volume: update.volume ?? null,
                },
              };
              const dailyVol = newDailyBar?.volume ?? null;
              const avgVol = prev.avg_volume;
              const relVol = dailyVol != null && avgVol != null && avgVol > 0
                ? Math.round((dailyVol / avgVol) * 100) / 100
                : prev.rel_volume;
              return { ...prev, snapshot: newSnapshot, rel_volume: relVol };
            });
          }
        } catch {
          // ignore parse errors
        }
      };

      // Do not reconnect from onerror alone -- browsers fire it just before onclose.
      ws.onerror = () => {
        if (!cancelled && mountedRef.current && ws === wsRef.current) {
          setLoading(false);
          setRefreshing(false);
          if (!initialReceived) setFetchFailed(true);
        }
      };
      ws.onclose = () => {
        if (!mountedRef.current || cancelled || ws !== wsRef.current) return;
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) {
          setFetchFailed(true);
        } else {
          setStale(true);
          setDisconnectedSince(prev => prev ?? Date.now());
        }
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, TICKER_WS_RECONNECT_CAP_MS);
        reconnectTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      window.clearTimeout(seedTimer);
      seedCtl.abort();
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [sample, symbol]);

  if (sample && symbol) {
    return {
      ...IDLE_STREAM,
      detail: sample.tickerDetail(symbol),
    };
  }

  return { detail, loading, refreshing, fetchFailed, stale, disconnectedSince };
}
