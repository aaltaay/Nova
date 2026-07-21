/** WebSocket ticker detail stream — Phase 1 fast snapshot, Phase 2 slow enrich, live trades. */
import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import type { BarData, TickerDetail, TickerTradeUpdate } from '../types/ticker';

const WS_URL = `${WS_BASE_URL}/ws`;

export function useTickerStream(symbol: string | null): {
  detail: TickerDetail | null;
  loading: boolean;
  refreshing: boolean;
  fetchFailed: boolean;
} {
  const sample = useSampleDataOptional();
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const hasDetailRef = useRef(false);

  useEffect(() => {
    if (sample) return;
    if (!symbol) {
      hasDetailRef.current = false;
      setDetail(null);
      setLoading(false);
      setRefreshing(false);
      setFetchFailed(false);
      return;
    }

    let cancelled = false;
    let initialReceived = false;

    // Symbol gate: never keep the previous ticker's detail while the new one loads.
    // Otherwise quote can show a new price (from scanner) while DepthLadder still
    // receives detail.symbol from the prior name (MVO quote + NXTC Level 2).
    hasDetailRef.current = false;
    setDetail(null);
    setFetchFailed(false);
    setLoading(true);
    setRefreshing(true);

    const ws = new WebSocket(`${WS_URL}/ticker/${symbol}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      if (cancelled || ws !== wsRef.current) return;
      try {
        const msg = JSON.parse(e.data);
        const msgSym = typeof msg.symbol === 'string' ? msg.symbol.toUpperCase() : null;
        if (msgSym != null && msgSym !== symbol) return;

        if (msg.type === 'initial') {
          const { type: _t, ...data } = msg;
          const next = data as TickerDetail;
          if (next.symbol && next.symbol.toUpperCase() !== symbol) return;
          initialReceived = true;
          hasDetailRef.current = true;
          setDetail(next);
          setLoading(false);
          setRefreshing(false);
          setFetchFailed(false);
        } else if (msg.type === 'detail_update') {
          if (!initialReceived) return;
          setDetail(prev => {
            if (!prev || prev.symbol.toUpperCase() !== symbol) return prev;
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
            };
          });
        } else if (msg.type === 'trade_update') {
          if (!initialReceived) return;
          const update = msg as TickerTradeUpdate;
          setDetail(prev => {
            if (!prev || prev.symbol.toUpperCase() !== symbol) return prev;
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
              // Keep Webull Pre: basis = prior close when IBKR sends prev_close.
              session_close: update.prev_close != null
                ? update.prev_close
                : prev.snapshot?.session_close ?? null,
              latest_trade: {
                price: newPrice,
                size: update.size ?? prev.snapshot?.latest_trade?.size ?? null,
                timestamp: update.timestamp ?? prev.snapshot?.latest_trade?.timestamp ?? null,
                exchange: prev.snapshot?.latest_trade?.exchange ?? null,
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

    ws.onerror = () => {
      if (!cancelled && ws === wsRef.current) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };
    ws.onclose = () => {
      if (!cancelled && ws === wsRef.current) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };

    return () => {
      cancelled = true;
      if (wsRef.current === ws) wsRef.current = null;
      ws.close();
    };
  }, [sample, symbol]);

  if (sample && symbol) {
    return {
      detail: sample.tickerDetail(symbol),
      loading: false,
      refreshing: false,
      fetchFailed: false,
    };
  }

  return { detail, loading, refreshing, fetchFailed };
}
