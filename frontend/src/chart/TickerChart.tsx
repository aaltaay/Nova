import { memo, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  CHART_DEFAULT_TIMEFRAME,
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_OSCILLATOR_MAX_PCT,
  CHART_GRID_OSCILLATOR_MIN_PCT,
  CHART_GRID_OSCILLATOR_PCT,
  CHART_GRID_OSCILLATOR_SPLIT_KEY,
  CHART_OSCILLATOR_IDS,
  type ChartIndicatorId,
  type ChartOscillatorId,
} from '../constants';
import { TickerChartErrorBoundary } from '../components/TickerChartErrorBoundary';
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
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { ChartPaneOverlays } from './ChartPaneOverlays';
import { findOpenPosition } from './positionOverlay';
import { useChartFeed } from './chartFeed';
import { RecordedPane } from './RecordedPane';
import { TickerChartCard } from './TickerChartCard';
import { chartHeightForVariant, tickerChartCardClass } from './tickerChartCard';
import type { ChartTradeUpdate, RenderPaneOverlay } from './types';
import { useRenderCount } from '../perf/useRenderCount';

export type { ChartTradeUpdate } from './types';

interface TickerChartProps {
  symbol: string;
  lastTrade?: ChartTradeUpdate | null;
  /** Follow the ticker stream for the live candle instead of `lastTrade`: a print is drawn with no render
   * of the chart (the Trader grid, #707). */
  followTicker?: boolean;
  variant?: 'panel' | 'page' | 'grid';
  fixedTimeframe?: string;
  title?: string;
  subtitle?: string;
  /** Override default indicator toggles (e.g. grid 1m/5m start with MACD on). */
  initialIndicators?: ChartIndicatorId[];
  /**
   * Controlled indicators (Trader grid: the shared desk toolbar owns them).
   * When set, `initialIndicators` is ignored and toggles go through
   * `onIndicatorToggle`.
   */
  indicators?: ChartIndicatorId[];
  onIndicatorToggle?: (id: ChartIndicatorId) => void;
  /** Controlled drawing tool shared across grid panes (see useChartDrawingManager). */
  activeTool?: string | null;
  onActiveToolChange?: (tool: string | null) => void;
  /** One-line header, no per-pane toolbar (desk toolbar lives above the grid). */
  compactChrome?: boolean;
  /** Highlight as the pane the desk toolbar's indicator toggles target. */
  focused?: boolean;
  /** Pointer-down on this pane -- desk toolbar retargets to it. */
  onFocusPane?: () => void;
  /** When false, pause bar polling and resize work (hidden Trader tab). */
  chartActive?: boolean;
  /** Grid-local maximize (#113). Header ⛶ is fullscreen, not this flag. */
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
  /** Double-click expands inside the 2x2; header ⛶ uses the Fullscreen API. */
  maximizeInGrid?: boolean;
  /** Bumps when the grid maximize layout flips so hidden siblings remeasure. */
  layoutEpoch?: string | null;
  /** What the page draws inside the pane (the Trader tab's stock read, ADR 036). */
  renderPaneOverlay?: RenderPaneOverlay;
}

/**
 * Memoized: the Trader page re-renders on every quote, and four panes drawing
 * again each time cost the desk its frame rate. A pane draws again when its own
 * props change (a trade, its indicators, the tool), never for its parent alone.
 */
export const TickerChart = memo(function TickerChart(props: TickerChartProps) {
  const feed = useChartFeed();
  return (
    <TickerChartErrorBoundary label={props.fixedTimeframe ?? props.title}>
      {feed.kind === 'recorded'
        ? <RecordedPane {...props} feed={feed} />
        : <LivePane {...props} />}
    </TickerChartErrorBoundary>
  );
});

function LivePane({
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
      chartApi={chartApi}
      candleSeriesRef={candleSeriesRef}
      volSeriesRef={volSeriesRef}
      vwapSource={vwapSource}
      accountOverlay
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
    </ChartPortalFrame>
  );
}
