import { useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CandlestickSeries, HistogramSeries, createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import { WorkspaceProvider } from '../../src/workspace/WorkspaceContext';
import { SimSessionHeader } from '../../src/sim/SimSessionHeader';
import { useChartBars } from '../../src/chart/useChartBars';
import { useChartLiveTrade } from '../../src/chart/useChartLiveTrade';
import { useVwapSourceBars } from '../../src/chart/useVwapSourceBars';
import { HistoricalTimeSales } from '../../src/sim/HistoricalTimeSales';
import { useHistoricalSnapshot } from '../../src/sim/useHistoricalSnapshot';
import { advanceSampleMinute, installSampleReplayApi } from './replayChartSampleApi';

const sampleApi = !new URLSearchParams(location.search).has('external-api');
if (sampleApi) installSampleReplayApi();
else document.getElementById('fixture-help')!.textContent = 'Replay component verification · configured API and actual archived data';

const futureTrade = { symbol: 'IMCC', price: 999, timestamp: '2026-09-18T23:00:00Z' };

function Chart() {
  const snapshot = useHistoricalSnapshot('IMCC', !sampleApi);
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const [painted, setPainted] = useState('[]');
  useLayoutEffect(() => {
    const chart = createChart(container.current!, { width: 800, height: 300 });
    chartRef.current = chart;
    const candles = chart.addSeries(CandlestickSeries);
    candleSeriesRef.current = candles;
    volSeriesRef.current = chart.addSeries(HistogramSeries);
    candles.subscribeDataChanged(() => setPainted(JSON.stringify(candles.data())));
    return () => { chart.remove(); chartRef.current = null; candleSeriesRef.current = null; volSeriesRef.current = null; };
  }, []);
  const live = useChartLiveTrade(candleSeriesRef, futureTrade, '1Min', 'IMCC');
  const state = useChartBars({ symbol: 'IMCC', timeframe: '1Min', chartRef,
    candleSeriesRef, volSeriesRef, lastCandleRef: live.lastCandleRef,
    lastTrade: futureTrade, applyLiveTrade: live.applyLiveTrade, onSeriesReset: live.resetTradeState });
  const vwap = useVwapSourceBars('IMCC', true);
  return <>
    {sampleApi && <button type="button" onClick={advanceSampleMinute}>Advance sample minute</button>}
    <div ref={container} />
    {snapshot?.active && <HistoricalTimeSales symbol="IMCC" snapshot={snapshot} />}
    <output data-testid="painted">{painted}</output>
    <output data-testid="indicators">{JSON.stringify(state.indicatorBars)}</output>
    <output data-testid="vwap">{JSON.stringify(vwap.bars)}</output>
    <output data-testid="error">{state.error}</output>
    <output data-testid="empty">{state.emptyText}</output>
  </>;
}

createRoot(document.getElementById('root')!).render(
  <WorkspaceProvider><SimSessionHeader active /><Chart /></WorkspaceProvider>,
);
