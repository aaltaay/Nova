/** The live desk pane. Loaded only when the feed is live, so /review does not fetch it. */

import { useRef, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  CHART_DEFAULT_TIMEFRAME,
} from '../constantGroups/market_ui';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_OSCILLATOR_MAX_PCT,
  CHART_GRID_OSCILLATOR_MIN_PCT,
  CHART_GRID_OSCILLATOR_PCT,
  CHART_GRID_OSCILLATOR_SPLIT_KEY,
  CHART_OSCILLATOR_IDS,
  type ChartIndicatorId,
  type ChartOscillatorId,
} from '../constantGroups/chart_api';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { toggleIndicator } from '../chartIndicators';
import { ChartPortalFrame } from './ChartPortalFrame';
import { useChartBars } from './useChartBars';
import { useChartDrawingManager } from './useChartDrawingManager';
import { claimChartDrawingHotkeyFocus } from './chartDrawingKeys';
import { useChartInstance } from './useChartInstance';
import { useChartLiveTrade } from './useChartLiveTrade';
import { useChartSessionHighlight } from './useChartSessionHighlight';
import { useChartBarCountdown } from './useChartBarCountdown';
import { useChartDrawingAxisLabels } from './useChartDrawingAxisLabels';
import { useTickerChartEscape } from './useTickerChartEscape';
import { useTickerChartMaximize } from './useTickerChartMaximize';
import { useVwapSourceBars } from './useVwapSourceBars';
import { useOptionalIbkrAccountContext } from '../ibkr';
import { ChartPaneOverlays } from './ChartPaneOverlays';
import { ChartAccountOverlay } from './ChartAccountOverlay';
import { findOpenPosition } from './positionOverlay';
import { TickerChartCard } from './TickerChartCardView';
import { chartHeightForVariant, tickerChartCardClass } from './tickerChartCard';
import { CandleHoverTip } from './CandleHoverTip';
import { useRenderCount } from '../perf/useRenderCount';
import type { TickerChartProps } from './TickerChart';

export function LivePane({
  symbol,
  lastTrade,
  followTicker = false,
  variant = 'panel',
  fixedTimeframe,
  title,
  subtitle,
  initialIndicators,
  indicators: controlledIndicators,
  onIndicatorToggle,
  activeTool: controlledTool,
  onActiveToolChange,
  compactChrome = false,
  focused = false,
  onFocusPane,
  chartActive = true,
  maximized: controlledMaximized,
  onMaximizeChange,
  maximizeInGrid = false,
  layoutEpoch = null,
  renderPaneOverlay,
}: TickerChartProps) {
  useRenderCount('TickerChart');
  const chartHeight = chartHeightForVariant(variant);

  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const drawingHotkeyOwnerRef = useRef(Symbol('chart-drawing-hotkeys'));

  const [userTimeframe, setUserTimeframe] = useState(
    fixedTimeframe ?? CHART_DEFAULT_TIMEFRAME,
  );
  const timeframe = fixedTimeframe ?? userTimeframe;
  const {
    maximized,
    headerMaximized,
    isFullscreen,
    setMaximized,
    toggleMaximize,
    portalMaximized,
    slotRef,
    host,
  } = useTickerChartMaximize({
    maximizeInGrid,
    maximized: controlledMaximized,
    onMaximizeChange,
  });
  const [localIndicators, setLocalIndicators] = useState<ChartIndicatorId[]>(
    () => [...(initialIndicators ?? CHART_DEFAULT_INDICATORS)],
  );
  const enabledIndicators = controlledIndicators ?? localIndicators;

  // Grid panes: oscillator block is a share of the card, dragged per pane.
  const { topPct: pricePct, onDragStart: onOscDragStart, reset: resetOscSplit } =
    useResizableHeight({
      storageKey: `${CHART_GRID_OSCILLATOR_SPLIT_KEY}.${timeframe}`,
      defaultPct: 100 - CHART_GRID_OSCILLATOR_PCT,
      minPct: 100 - CHART_GRID_OSCILLATOR_MAX_PCT,
      maxPct: 100 - CHART_GRID_OSCILLATOR_MIN_PCT,
      containerRef: cardRef,
    });

  // Panel: fill the Quote Panel slot so LWC (incl. time axis) fits under
  // header/toolbar instead of painting 280px and getting clipped by max-height.
  const fillParentHeight = variant === 'grid' || variant === 'panel' || maximized;
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
    layoutEpoch,
  });

  const { restoreAfterStorePaint, lastCandleRef, resetTradeState, liveTipTime } = useChartLiveTrade(
    candleSeriesRef,
    volSeriesRef,
    lastTrade,
    timeframe,
    symbol,
    followTicker,
  );

  const {
    loading, error, emptyText, usingMock, indicatorBars, filling, coverageAsOf,
    historyError, historyErrorTs,
  } = useChartBars({
    symbol,
    timeframe,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    lastCandleRef,
    lastTrade,
    restoreAfterStorePaint,
    onSeriesReset: resetTradeState,
    chartActive,
  });

  const barsRevision =
    indicatorBars.length +
    (typeof indicatorBars[0]?.time === 'number' ? indicatorBars[0].time : 0) +
    (typeof indicatorBars[indicatorBars.length - 1]?.time === 'number'
      ? (indicatorBars[indicatorBars.length - 1].time as number)
      : 0);

  // Below useChartBars on purpose: hydrating drawings needs the painted series
  // so anchors can snap onto this pane's bar grid (ADR 015).
  const {
    activeTool,
    setActiveTool,
    handleToolClick,
    handleClearAll,
    selection,
    updateSelectedDrawingColor,
  } = useChartDrawingManager({
    containerRef,
    chartRef,
    candleSeriesRef,
    chartApi,
    symbol,
    seriesRevision: barsRevision,
    hotkeyOwner: drawingHotkeyOwnerRef.current,
    activeTool: controlledTool,
    onActiveToolChange,
  });

  useChartSessionHighlight({
    chartApi,
    candleSeriesRef,
    timeframe,
    barsRevision,
  });

  // Minute panes count down to the forming candle's close on the venue's clock.
  useChartBarCountdown({ chartApi, candleSeriesRef, timeframe, chartActive });

  // Price-level drawings put their price on the axis, not clipped in the plot.
  useChartDrawingAxisLabels({ candleSeriesRef, symbol, seriesRevision: barsRevision });

  // One 04:00-anchored VWAP for every pane, not a per-timeframe accumulation.
  const vwapSource = useVwapSourceBars(symbol, chartActive);

  useTickerChartEscape(activeTool, setActiveTool, headerMaximized, setMaximized);

  const account = useOptionalIbkrAccountContext();
  const openPosition = findOpenPosition(account?.positions ?? [], symbol);

  function handleIndicatorToggle(id: ChartIndicatorId) {
    if (onIndicatorToggle) {
      onIndicatorToggle(id);
      return;
    }
    setLocalIndicators(prev => toggleIndicator(prev, id));
  }

  const gridOscillators = variant === 'grid' && oscillatorEnabled.length > 0;
  const cardClass = tickerChartCardClass({ variant, maximized, compactChrome, focused });

  const card = (
    <TickerChartCard
      cardRef={cardRef}
      containerRef={containerRef}
      cardClass={cardClass}
      symbol={symbol}
      timeframe={timeframe}
      indicatorBars={indicatorBars}
      barsRevision={barsRevision}
      filling={filling}
      focused={focused}
      positionAvg={openPosition ? String(openPosition.avgCost) : undefined}
      positionQty={openPosition ? String(openPosition.qty) : undefined}
      gridOscillators={gridOscillators}
      pricePct={pricePct}
      activeTool={activeTool}
      enabledIndicators={enabledIndicators}
      lockTimeframe={lockTimeframe}
      headerMaximized={headerMaximized}
      subtitle={subtitle}
      title={title}
      usingMock={usingMock}
      compactChrome={compactChrome}
      keepCompactWhenMaximized={maximizeInGrid && !isFullscreen}
      useFullscreenExpand={maximizeInGrid}
      coverageAsOf={coverageAsOf}
      historyError={historyError}
      selection={selection}
      onClearAll={handleClearAll}
      onColorChange={updateSelectedDrawingColor}
      onIndicatorToggle={handleIndicatorToggle}
      onMaximize={toggleMaximize}
      onTimeframeChange={setUserTimeframe}
      onToolClick={handleToolClick}
      onPointerDown={() => {
        claimChartDrawingHotkeyFocus(drawingHotkeyOwnerRef.current);
        onFocusPane?.();
      }}
      onPointerEnter={() => claimChartDrawingHotkeyFocus(drawingHotkeyOwnerRef.current)}
      loading={loading}
      error={error}
      emptyText={emptyText}
      historyErrorTs={historyErrorTs}
      paneOverlay={(
        <ChartPaneOverlays
          symbol={symbol}
          timeframe={timeframe}
          barCount={indicatorBars.length}
          barsRevision={barsRevision}
          chart={chartApi}
          candleSeriesRef={candleSeriesRef}
          containerRef={containerRef}
          activeTool={activeTool}
          onToolClick={handleToolClick}
          enabledIndicators={enabledIndicators}
          onIndicatorToggle={handleIndicatorToggle}
          renderOverlay={renderPaneOverlay}
        />
      )}
      hover={(
        <CandleHoverTip
          chart={chartApi}
          candleSeriesRef={candleSeriesRef}
          volSeriesRef={volSeriesRef}
          containerRef={containerRef}
          symbol={symbol}
          timeframe={timeframe}
          paneBars={indicatorBars}
          vwapSource={vwapSource}
        />
      )}
      chartApi={chartApi}
      candleSeriesRef={candleSeriesRef}
      volSeriesRef={volSeriesRef}
      vwapSource={vwapSource}
      liveTipTime={liveTipTime}
      onOscDragStart={onOscDragStart}
      resetOscSplit={resetOscSplit}
      oscillatorEnabled={oscillatorEnabled}
      variant={variant}
    />
  );

  return (
    <ChartPortalFrame
      slotRef={slotRef}
      host={host}
      portalMaximized={portalMaximized}
      chartHeight={chartHeight}
    >
      {card}
      <ChartAccountOverlay
        chart={chartApi}
        candleSeriesRef={candleSeriesRef}
        symbol={symbol}
        timeframe={timeframe}
        bars={indicatorBars}
        barsRevision={barsRevision}
      />
    </ChartPortalFrame>
  );
}
