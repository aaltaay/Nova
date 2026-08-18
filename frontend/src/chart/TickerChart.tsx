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
  /** Override default indicator toggles (e.g. grid 1m/5m start with MACD on). */
  initialIndicators?: ChartIndicatorId[];
  /** When false, pause bar polling and resize work (hidden Trader tab). */
  chartActive?: boolean;
}

export function TickerChart(props: TickerChartProps) {
  // Soft-reset on symbol change inside Inner -- avoid remounting the whole LWC tree.
  return (
    <TickerChartErrorBoundary>
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
  initialIndicators,
  chartActive = true,
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
  const timeframe = fixedTimeframe ?? userTimeframe;
  const [maximized, setMaximized] = useState(false);
  const [enabledIndicators, setEnabledIndicators] = useState<ChartIndicatorId[]>(
    () => [...(initialIndicators ?? CHART_DEFAULT_INDICATORS)],
  );

  // Panel: fill the Quote Panel slot so LWC (incl. time axis) fits under
  // header/toolbar instead of painting 280px and getting clipped by max-height.
  const fillParentHeight = variant === 'grid' || variant === 'panel' || maximized;
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
    timeframe,
    chartActive,
    oscillatorPaneCount: oscillatorEnabled.length,
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

  const { loading, error, usingMock, indicatorBars, filling, coverageAsOf } = useChartBars({
    symbol,
    timeframe,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    lastCandleRef,
    lastTrade,
    applyLiveTrade,
    onSeriesReset: resetTradeState,
    chartActive,
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
        {loading && indicatorBars.length === 0 && (
          <div className="chart-overlay">Loading…</div>
        )}
        {!loading && filling && indicatorBars.length === 0 && !error && (
          <div className="chart-overlay chart-overlay--info">
            Loading IBKR historical…
          </div>
        )}
        {!loading && error && indicatorBars.length === 0 && (
          <div className="chart-overlay chart-overlay--error">{error}</div>
        )}
        {filling && indicatorBars.length > 0 && (
          <div className="chart-filling-hint">
            {coverageAsOf
              ? `as of ${coverageAsOf.slice(11, 16)} ET, filling…`
              : 'filling…'}
          </div>
        )}
      </div>
      <TickerChartOverlays
        chart={chartApi}
        bars={indicatorBars}
        barsRevision={barsRevision}
        enabled={enabledIndicators}
      />
      {oscillatorEnabled.length > 0 && (
        <TickerChartOscillatorPanes
          parentChart={chartApi}
          bars={indicatorBars}
          barsRevision={barsRevision}
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
