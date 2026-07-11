/** WebSocket ticker detail stream — Phase 1 fast snapshot, Phase 2 slow enrich, live trades. */
import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from '../constants';
import type { BarData, TickerDetail, TickerTradeUpdate } from '../types/ticker';

const WS_URL = `${WS_BASE_URL}/ws`;

export function useTickerStream(symbol: string | null): {
  detail: TickerDetail | null;
  loading: boolean;
  refreshing: boolean;
  fetchFailed: boolean;
} {
  const [detail, setDetail] = useState<TickerDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchFailed, setFetchFailed] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const hasDetailRef = useRef(false);

  useEffect(() => {
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

    setFetchFailed(false);
    setLoading(!hasDetailRef.current);
    setRefreshing(true);

    const ws = new WebSocket(`${WS_URL}/ticker/${symbol}`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      if (cancelled) return;
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === 'initial') {
          const { type: _t, ...data } = msg;
          initialReceived = true;
          hasDetailRef.current = true;
          setDetail(data as TickerDetail);
          setLoading(false);
          setRefreshing(false);
          setFetchFailed(false);
        } else if (msg.type === 'detail_update') {
          setDetail(prev => {
            if (!prev) return prev;
            return {
              ...prev,
              news: msg.news ?? prev.news,
              fundamentals: msg.fundamentals ?? prev.fundamentals,
              avg_volume: msg.avg_volume ?? prev.avg_volume,
              rel_volume: msg.rel_volume ?? prev.rel_volume,
              news_impact: msg.news_impact ?? prev.news_impact,
            };
          });
        } else if (msg.type === 'trade_update') {
          const update = msg as TickerTradeUpdate;
          setDetail(prev => {
            if (!prev) return prev;
            const newPrice = update.price;
            const prevDailyBar = prev.snapshot?.daily_bar ?? null;
            const newDailyBar: BarData | null = update.volume != null
              ? {
                  open: null, high: null, low: null, close: null,
                  trade_count: null, vwap: null, timestamp: null,
                  ...prevDailyBar,
                  volume: update.volume,
                }
              : prevDailyBar;
            const newSnapshot = {
              ...prev.snapshot,
              daily_bar: newDailyBar,
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
      if (!cancelled) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };
    ws.onclose = () => {
      if (!cancelled) {
        setLoading(false);
        setRefreshing(false);
        if (!initialReceived) setFetchFailed(true);
      }
    };

    return () => {
      cancelled = true;
      wsRef.current = null;
      ws.close();
    };
  }, [symbol]);

  return { detail, loading, refreshing, fetchFailed };
}
