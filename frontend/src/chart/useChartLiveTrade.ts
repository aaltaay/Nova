/** ADR 005 — monotonic live-trade candle merging into the open bar. */

import { useCallback, useEffect, useRef } from 'react';
import type { CandlestickData, ISeriesApi, Time } from 'lightweight-charts';
import { isOutOfOrderTrade, tradeBucket } from '../tickerChartData';
import { tradeMatchesChartSymbol } from './liveTradeGate';
import type { ChartTradeUpdate } from './types';

export function useChartLiveTrade(
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>,
  lastTrade: ChartTradeUpdate | null | undefined,
  timeframe: string,
  chartSymbol: string,
) {
  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);

  const applyLiveTrade = useCallback((trade: ChartTradeUpdate, tf: string) => {
    if (!trade.price || !trade.timestamp || !candleSeriesRef.current) return;
    if (!tradeMatchesChartSymbol(chartSymbol, trade.symbol)) return;
    const daily = tf === '1Day' || tf === '1Week' || tf === '1Month';
    if (daily) return;

    const bucket = tradeBucket(trade.timestamp, tf);
    if (bucket === null) return;
    const prev = lastCandleRef.current;
    if (isOutOfOrderTrade(prev, bucket)) return;
    const price = trade.price;

    if (prev && prev.time === bucket) {
      const updated: CandlestickData<Time> = {
        time: bucket,
        open: prev.open,
        high: Math.max(prev.high, price),
        low: Math.min(prev.low, price),
        close: price,
      };
      candleSeriesRef.current.update(updated);
      lastCandleRef.current = updated;
    } else {
      const newCandle: CandlestickData<Time> = {
        time: bucket, open: price, high: price, low: price, close: price,
      };
      candleSeriesRef.current.update(newCandle);
      lastCandleRef.current = newCandle;
    }
  }, [candleSeriesRef, chartSymbol]);

  useEffect(() => {
    if (!lastTrade?.price || !lastTrade.timestamp) return;
    if (!tradeMatchesChartSymbol(chartSymbol, lastTrade.symbol)) return;
    if (lastTrade.timestamp === prevTradeTsRef.current) return;
    prevTradeTsRef.current = lastTrade.timestamp;
    applyLiveTrade(lastTrade, timeframe);
  }, [lastTrade, timeframe, applyLiveTrade, chartSymbol]);

  const resetTradeState = useCallback(() => {
    prevTradeTsRef.current = null;
    lastCandleRef.current = null;
  }, []);

  return { applyLiveTrade, lastCandleRef, resetTradeState };
}
