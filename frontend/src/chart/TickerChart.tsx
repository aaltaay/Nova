import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  CHART_DEFAULT_TIMEFRAME,
  CHART_HEIGHT_PANEL,
  CHART_HEIGHT_PAGE,
  CHART_HEIGHT_GRID,
  CHART_DEFAULT_INDICATORS,
  CHART_OSCILLATOR_IDS,
  type ChartIndicatorId,
  type ChartOscillatorId,
} from '../constants';
import { TickerChartControls } from '../components/TickerChartControls';
import { TickerChartErrorBoundary } from '../components/TickerChartErrorBoundary';
import { TickerChartOverlays } from '../components/TickerChartOverlays';
import { TickerChartOscillatorPanes } from '../components/TickerChartOscillatorPanes';
import { useMaximizedChartPortal } from '../hooks/useMaximizedChartPortal';
import { toggleIndicator } from '../chartIndicators';
import { useChartBars } from './useChartBars';
import { useChartDrawingManager } from './useChartDrawingManager';
import { useChartInstance } from './useChartInstance';
import { useChartLiveTrade } from './useChartLiveTrade';
import { useChartSessionHighlight } from './useChartSessionHighlight';
import type { ChartTradeUpdate } from './types';

export type { ChartTradeUpdate } from './types';

interface TickerChartProps {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  variant?: 'panel' | 'page' | 'grid';
  fixedTimeframe?: string;
  title?: string;
  subtitle?: string;
}

export function TickerChart(props: TickerChartProps) {
  return (
    <TickerChartErrorBoundary key={props.symbol}>
      <TickerChartInner {...props} />
    </TickerChartErrorBoundary>
  );
}

function TickerChartInner({
  symbol,
  lastTrade,
  variant = 'panel',
  fixedTimeframe,
  title,
  subtitle,
}: TickerChartProps) {
  const chartHeight =
    variant === 'grid' ? CHART_HEIGHT_GRID
    : variant === 'page' ? CHART_HEIGHT_PAGE
    : CHART_HEIGHT_PANEL;

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  const [userTimeframe, setUserTimeframe] = useState(
    fixedTimeframe ?? CHART_DEFAULT_TIMEFRAME,
  );
  // Prefer prop when locked; avoid syncing prop→state in an effect.
  const timeframe = fixedTimeframe ?? userTimeframe;
  const [maximized, setMaximized] = useState(false);
  const [enabledIndicators, setEnabledIndicators] = useState<ChartIndicatorId[]>(
    () => [...CHART_DEFAULT_INDICATORS],
  );

  const fillParentHeight = variant === 'grid' || maximized;
  const { slotRef, host } = useMaximizedChartPortal(maximized);
  const lockTimeframe = !!fixedTimeframe;
  const oscillatorEnabled = enabledIndicators.filter((id): id is ChartOscillatorId =>
    (CHART_OSCILLATOR_IDS as readonly ChartOscillatorId[]).includes(id as ChartOscillatorId),
  );

  const chartApi = useChartInstance({
    containerRef,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    chartHeight,
    fillParentHeight,
    maximized,
  });

  const {
    activeTool,
    setActiveTool,
    handleToolClick,
    handleClearAll,
  } = useChartDrawingManager({
    containerRef,
    chartRef,
    candleSeriesRef,
    chartApi,
  });

  const { applyLiveTrade, lastCandleRef, resetTradeState } = useChartLiveTrade(
    candleSeriesRef,
    lastTrade,
    timeframe,
    symbol,
  );

  const { loading, error, usingMock, indicatorBars } = useChartBars({
    symbol,
    timeframe,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    lastCandleRef,
    lastTrade,
    applyLiveTrade,
    onSeriesReset: resetTradeState,
  });

  const barsRevision =
    indicatorBars.length +
    (typeof indicatorBars[0]?.time === 'number' ? indicatorBars[0].time : 0) +
    (typeof indicatorBars[indicatorBars.length - 1]?.time === 'number'
      ? (indicatorBars[indicatorBars.length - 1].time as number)
      : 0);

  const sessionHighlight = useChartSessionHighlight({
    chartApi,
    candleSeriesRef,
    timeframe,
    barsRevision,
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (activeTool) {
        setActiveTool(null);
        return;
      }
      if (maximized) setMaximized(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeTool, maximized, setActiveTool]);

  function handleMaximize() {
    setMaximized(m => !m);
  }

  function handleIndicatorToggle(id: ChartIndicatorId) {
    setEnabledIndicators(prev => toggleIndicator(prev, id));
  }

  const card = (
    <div className={`chart-card${maximized ? ' chart-card--maximized' : ''}${variant === 'grid' ? ' chart-card--grid' : ''}`}>
      <TickerChartControls
        activeTool={activeTool}
        enabledIndicators={enabledIndicators}
        lockTimeframe={lockTimeframe}
        maximized={maximized}
        showSessionLegend={sessionHighlight}
        subtitle={subtitle}
        timeframe={timeframe}
        title={title}
        usingMock={usingMock}
        onClearAll={handleClearAll}
        onIndicatorToggle={handleIndicatorToggle}
        onMaximize={handleMaximize}
        onTimeframeChange={setUserTimeframe}
        onToolClick={handleToolClick}
      />

      <div className="chart-body" ref={containerRef}>
        {loading && <div className="chart-overlay">Loading…</div>}
        {!loading && error && <div className="chart-overlay chart-overlay--error">{error}</div>}
      </div>
      <TickerChartOverlays
        chart={chartApi}
        bars={indicatorBars}
        enabled={enabledIndicators}
      />
      {oscillatorEnabled.length > 0 && (
        <TickerChartOscillatorPanes
          parentChart={chartApi}
          bars={indicatorBars}
          enabled={oscillatorEnabled}
        />
      )}
    </div>
  );

  return (
    <div
      ref={slotRef}
      className={`chart-portal-slot${maximized ? ' chart-portal-slot--maximized' : ''}`}
      style={maximized ? { minHeight: chartHeight } : undefined}
    >
      {createPortal(card, host)}
    </div>
  );
}
