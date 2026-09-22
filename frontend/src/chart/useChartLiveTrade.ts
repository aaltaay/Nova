/** ADR 005 -- monotonic live-trade candle merging into the open bar. */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CandlestickData, ISeriesApi, Time } from 'lightweight-charts';
import { mergeLiveTradeCandle } from './liveTradeApply';
import { tradeMatchesChartSymbol } from './liveTradeGate';
import type { ChartTradeUpdate } from './types';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { getBarsEntry } from './barsStore';

export function useChartLiveTrade(
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>,
  lastTrade: ChartTradeUpdate | null | undefined,
  timeframe: string,
  chartSymbol: string,
) {
  const sim = useIbkrStatus().mode === 'sim';
  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);
  const liveTipTimeRef = useRef<number | null>(null);
  const [liveTipTime, setLiveTipTime] = useState<number | null>(null);

  const applyLiveTrade = useCallback((trade: ChartTradeUpdate, tf: string) => {
    if (sim || getBarsEntry(chartSymbol, tf)?.coverage?.replay) return;
    if (!trade.price || !trade.timestamp || !candleSeriesRef.current) return;
    if (!tradeMatchesChartSymbol(chartSymbol, trade.symbol)) return;

    const next = mergeLiveTradeCandle(lastCandleRef.current, {
      price: trade.price,
      timestamp: trade.timestamp,
      source: trade.source,
    }, tf);
    if (!next) return;

    try {
      candleSeriesRef.current.update(next);
      lastCandleRef.current = next;
      if (typeof next.time === 'number' && next.time !== liveTipTimeRef.current) {
        liveTipTimeRef.current = next.time;
        setLiveTipTime(next.time);
      }
    } catch {
      /* series not ready / LWC rejected -- next paint will reset tip */
    }
  }, [candleSeriesRef, chartSymbol, sim]);

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
    liveTipTimeRef.current = null;
    setLiveTipTime(null);
  }, []);

  return { applyLiveTrade, lastCandleRef, resetTradeState, liveTipTime };
}
