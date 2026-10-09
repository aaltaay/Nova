/**
 * ADR 005 -- monotonic live-trade candle merging into the open bar, with its volume.
 *
 * The 10-second pane has one writer (#721): while the tape feeds it (`tapeOwns10Sec`) its forming
 * candle is the tape's prints, keyed by IBKR's second; a Level 1 trade, stamped on Nova's clock
 * when its tick lands, opened the next candle while prints still filled the last one.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CandlestickData, ISeriesApi, Time } from 'lightweight-charts';
import {
  countsLiveVolume,
  EMPTY_LIVE_VOLUME,
  mergeLiveTradeCandle,
  restoreLiveTip,
  shownTipVolume,
  stepLiveVolume,
  type LiveTip,
  type LiveVolumeState,
} from './liveTradeApply';
import { tradeMatchesChartSymbol } from './liveTradeGate';
import type { ChartTradeUpdate } from './types';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { useSimChartReplays } from './simChartReplays';
import { IDLE_TICKER, subscribeTicker, tickerLastTrade, tickerState } from '../hooks/tickerStore';
import { useSampleDataOptional } from '../sample_data/SampleDataContext';
import { getBarsEntry, tapeOwns10Sec } from './barsStore';
import { volumeBarColor } from '../tickerChartData';

export function useChartLiveTrade(
  candleSeriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>,
  volSeriesRef: React.RefObject<ISeriesApi<'Histogram'> | null>,
  lastTrade: ChartTradeUpdate | null | undefined,
  timeframe: string,
  chartSymbol: string,
  /** Read the ticker stream for prints instead of `lastTrade` (the Trader grid, #707). */
  followTicker = false,
) {
  /** Sim off the live edge: the replay owns the candles and live prints stay off them. */
  const sim = useSimChartReplays(useIbkrStatus().mode === 'sim');
  const sample = useSampleDataOptional();
  /** The newest trade, from `lastTrade` or the stream: what a repaint of the store puts back. */
  const latestTradeRef = useRef<ChartTradeUpdate | null | undefined>(lastTrade);
  /** The series' newest candle: the store's tip after a paint, the live tip after a trade. */
  const lastCandleRef = useRef<CandlestickData<Time> | null>(null);
  const liveTipRef = useRef<LiveTip | null>(null);
  const liveVolumeRef = useRef<LiveVolumeState>(EMPTY_LIVE_VOLUME);
  /** The store's newest bar as last painted: its time and volume. */
  const storeTipRef = useRef<{ time: Time; volume: number | null } | null>(null);
  const prevTradeTsRef = useRef<string | null>(null);
  const liveTipTimeRef = useRef<number | null>(null);
  const [liveTipTime, setLiveTipTime] = useState<number | null>(null);

  const replayOwnsBars = useCallback(
    (tf: string) => sim || Boolean(getBarsEntry(chartSymbol, tf)?.coverage?.replay),
    [chartSymbol, sim],
  );

  /** Draw one tip on the series; false when LWC refused it. */
  const paintTip = useCallback((candle: CandlestickData<Time>, volume: number | null) => {
    const candles = candleSeriesRef.current;
    if (!candles) return false;
    try {
      candles.update(candle);
      if (volume !== null) {
        volSeriesRef.current?.update({
          time: candle.time,
          value: volume,
          color: volumeBarColor(candle.open, candle.close),
        });
      }
    } catch {
      /* series not ready / LWC rejected -- next paint will reset tip */
      return false;
    }
    lastCandleRef.current = candle;
    if (typeof candle.time === 'number' && candle.time !== liveTipTimeRef.current) {
      liveTipTimeRef.current = candle.time;
      setLiveTipTime(candle.time);
    }
    return true;
  }, [candleSeriesRef, volSeriesRef]);

  /** The tape paints this pane's tip: drop any Level 1 tip it held. */
  const tapeOwnsTip = useCallback((tf: string) => {
    if (tf !== '10Sec' || !tapeOwns10Sec(chartSymbol)) return false;
    liveTipRef.current = null;
    return true;
  }, [chartSymbol]);

  const applyLiveTrade = useCallback((trade: ChartTradeUpdate, tf: string) => {
    if (replayOwnsBars(tf) || tapeOwnsTip(tf)) return;
    if (!trade.price || !trade.timestamp || !candleSeriesRef.current) return;
    if (!tradeMatchesChartSymbol(chartSymbol, trade.symbol)) return;

    const next = mergeLiveTradeCandle(lastCandleRef.current, {
      price: trade.price,
      timestamp: trade.timestamp,
      source: trade.source,
    }, tf);
    if (!next) return;

    let live: number | null = null;
    if (countsLiveVolume(tf)) {
      liveVolumeRef.current = stepLiveVolume(liveVolumeRef.current, next.time, trade.dayVolume);
      live = liveVolumeRef.current.volume;
    }
    const store = storeTipRef.current?.time === next.time ? storeTipRef.current.volume : null;
    if (paintTip(next, shownTipVolume(live, store))) {
      liveTipRef.current = { candle: next, volume: live };
    }
  }, [candleSeriesRef, chartSymbol, paintTip, replayOwnsBars, tapeOwnsTip]);

  /**
   * After the store repainted the series (`lastCandleRef` is now its newest
   * candle): put the live tip back, or -- with none yet -- merge the last trade.
   */
  const restoreAfterStorePaint = useCallback((
    storeTipVolume: number | null,
    trade: ChartTradeUpdate | null | undefined,
    tf: string,
  ) => {
    const storeCandle = lastCandleRef.current;
    storeTipRef.current = storeCandle ? { time: storeCandle.time, volume: storeTipVolume } : null;
    if (replayOwnsBars(tf) || tapeOwnsTip(tf)) return;
    const live = liveTipRef.current;
    if (live === null) {
      const newest = trade ?? latestTradeRef.current;
      if (newest?.price && newest.timestamp) applyLiveTrade(newest, tf);
      return;
    }
    const restored = restoreLiveTip(
      storeCandle ? { candle: storeCandle, volume: storeTipVolume } : null,
      live,
    );
    if (restored === null) {
      liveTipRef.current = null;
      return;
    }
    if (!paintTip(restored.candle, restored.volume)) liveTipRef.current = null;
    else liveTipRef.current = { candle: restored.candle, volume: live.volume };
  }, [applyLiveTrade, paintTip, replayOwnsBars, tapeOwnsTip]);

  /** Draw a trade unless it is the one drawn last. */
  const takeTrade = useCallback((trade: ChartTradeUpdate | null | undefined) => {
    latestTradeRef.current = trade;
    if (!trade?.price || !trade.timestamp) return;
    if (!tradeMatchesChartSymbol(chartSymbol, trade.symbol)) return;
    if (trade.timestamp === prevTradeTsRef.current) return;
    prevTradeTsRef.current = trade.timestamp;
    applyLiveTrade(trade, timeframe);
  }, [applyLiveTrade, chartSymbol, timeframe]);

  useEffect(() => {
    if (followTicker) return;
    takeTrade(lastTrade);
  }, [followTicker, lastTrade, takeTrade]);

  // Following the stream, a print goes to the series as it comes and the chart is not rendered for it.
  // The sample desk has no stream: its fixed last trade is drawn once.
  useEffect(() => {
    if (!followTicker) return;
    const key = chartSymbol.trim().toUpperCase();
    if (sample) {
      takeTrade(tickerLastTrade({ ...IDLE_TICKER, detail: sample.tickerDetail(chartSymbol) }, key));
      return;
    }
    const read = () => takeTrade(tickerLastTrade(tickerState(key), key));
    read();
    return subscribeTicker(key, read);
  }, [followTicker, sample, chartSymbol, takeTrade]);

  const resetTradeState = useCallback(() => {
    prevTradeTsRef.current = null;
    lastCandleRef.current = null;
    liveTipRef.current = null;
    liveVolumeRef.current = EMPTY_LIVE_VOLUME;
    storeTipRef.current = null;
    liveTipTimeRef.current = null;
    setLiveTipTime(null);
  }, []);

  return { restoreAfterStorePaint, lastCandleRef, resetTradeState, liveTipTime };
}
