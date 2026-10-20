/** A desk pane painted from a recorded feed. No live hooks, no orders, no saved drawings. */

import { useMemo, useRef, useState } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { CHART_DEFAULT_TIMEFRAME } from '../constantGroups/market_ui';
import {
  CHART_DEFAULT_INDICATORS,
  CHART_GRID_OSCILLATOR_MAX_PCT,
  CHART_GRID_OSCILLATOR_MIN_PCT,
  CHART_GRID_OSCILLATOR_PCT,
  CHART_GRID_OSCILLATOR_SPLIT_KEY,
  type ChartIndicatorId,
} from '../constantGroups/chart_api';
import { rawBarsToIndicatorBars } from '../chartIndicators';
import { toggleIndicator } from '../chartIndicators';
import { useResizableHeight } from '../hooks/useResizableHeight';
import { ChartPortalFrame } from './ChartPortalFrame';
import { claimChartDrawingHotkeyFocus } from './chartDrawingKeys';
import { useChartInstance } from './useChartInstance';
import { useChartSessionHighlight } from './useChartSessionHighlight';
import { useEphemeralDrawings } from './useEphemeralDrawings';
import { useRecordedBars } from './useRecordedBars';
import { useClearRecordedDrawings, useRecordedClearToken, useReportPanePainted, type RecordedChartFeed } from './chartFeed';
import { useTickerChartEscape } from './useTickerChartEscape';
import { useTickerChartMaximize } from './useTickerChartMaximize';
import { coversSessionOpen } from './vwapSession';
import { chartHeightForVariant, tickerChartCardClass } from './tickerChartCard';
import { oscillatorIds, TickerChartCard } from './TickerChartCardView';
import { useRenderCount } from '../perf/useRenderCount';
import type { RenderPaneOverlay } from './types';

export function RecordedPane({
  feed,
  symbol,
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
}: {
  feed: RecordedChartFeed;
  symbol: string;
  variant?: 'panel' | 'page' | 'grid';
  fixedTimeframe?: string;
  title?: string;
  subtitle?: string;
  initialIndicators?: ChartIndicatorId[];
  indicators?: ChartIndicatorId[];
  onIndicatorToggle?: (id: ChartIndicatorId) => void;
  activeTool?: string | null;
  onActiveToolChange?: (tool: string | null) => void;
  compactChrome?: boolean;
  focused?: boolean;
  onFocusPane?: () => void;
  chartActive?: boolean;
  maximized?: boolean;
  onMaximizeChange?: (next: boolean) => void;
  maximizeInGrid?: boolean;
  layoutEpoch?: string | null;
  renderPaneOverlay?: RenderPaneOverlay;
}) {
  useRenderCount('TickerChart');
  const chartHeight = chartHeightForVariant(variant);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const drawingHotkeyOwnerRef = useRef(Symbol('chart-drawing-hotkeys'));
  const [userTimeframe, setUserTimeframe] = useState(fixedTimeframe ?? CHART_DEFAULT_TIMEFRAME);
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
  const [localTool, setLocalTool] = useState<string | null>(null);
  const enabledIndicators = controlledIndicators ?? localIndicators;
  const activeTool = controlledTool !== undefined ? controlledTool : localTool;
  const { topPct: pricePct, onDragStart: onOscDragStart, reset: resetOscSplit } =
    useResizableHeight({
      storageKey: `${CHART_GRID_OSCILLATOR_SPLIT_KEY}.${timeframe}`,
      defaultPct: 100 - CHART_GRID_OSCILLATOR_PCT,
      minPct: 100 - CHART_GRID_OSCILLATOR_MAX_PCT,
      maxPct: 100 - CHART_GRID_OSCILLATOR_MIN_PCT,
      containerRef: cardRef,
    });
  const fillParentHeight = variant === 'grid' || variant === 'panel' || maximized;
  const oscillatorEnabled = oscillatorIds(enabledIndicators);
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
  const report = useReportPanePainted();
  const clearToken = useRecordedClearToken();
  const clearRecorded = useClearRecordedDrawings();
  const { indicatorBars, barsRevision } = useRecordedBars({
    feed,
    timeframe,
    chartRef,
    candleSeriesRef,
    volSeriesRef,
    chartApi,
    onPainted: () => report?.(`${feed.symbol}:${timeframe}`),
  });
  useChartSessionHighlight({ chartApi, candleSeriesRef, timeframe, barsRevision });
  useEphemeralDrawings({
    containerRef,
    chartRef,
    candleSeriesRef,
    chartApi,
    activeTool,
    clearToken,
  });
  const vwapIndicator = useMemo(
    () => rawBarsToIndicatorBars(feed.vwapBars, '1Min'),
    [feed.vwapBars],
  );
  const vwapSource = useMemo(() => ({
    bars: vwapIndicator,
    revision: vwapIndicator.length,
    coversOpen: coversSessionOpen(vwapIndicator),
  }), [vwapIndicator]);
  useTickerChartEscape(activeTool, (tool) => {
    onActiveToolChange?.(tool);
    if (controlledTool === undefined) setLocalTool(tool);
  }, headerMaximized, setMaximized);

  function handleIndicatorToggle(id: ChartIndicatorId) {
    if (onIndicatorToggle) {
      onIndicatorToggle(id);
      return;
    }
    setLocalIndicators((prev) => toggleIndicator(prev, id));
  }

  function handleToolClick(toolId: string) {
    const next = activeTool === toolId ? null : toolId;
    onActiveToolChange?.(next);
    if (controlledTool === undefined) setLocalTool(next);
  }

  const gridOscillators = variant === 'grid' && oscillatorEnabled.length > 0;
  const card = (
    <TickerChartCard
      cardRef={cardRef}
      containerRef={containerRef}
      cardClass={tickerChartCardClass({ variant, maximized, compactChrome, focused })}
      symbol={symbol}
      timeframe={timeframe}
      indicatorBars={indicatorBars}
      barsRevision={barsRevision}
      filling={false}
      focused={focused}
      gridOscillators={gridOscillators}
      pricePct={pricePct}
      activeTool={activeTool}
      enabledIndicators={enabledIndicators}
      lockTimeframe={Boolean(fixedTimeframe)}
      headerMaximized={headerMaximized}
      subtitle={subtitle}
      title={title}
      usingMock={false}
      compactChrome={compactChrome}
      keepCompactWhenMaximized={maximizeInGrid && !isFullscreen}
      useFullscreenExpand={maximizeInGrid}
      coverageAsOf={null}
      historyError={null}
      selection={null}
      onClearAll={() => {
        clearRecorded();
        onActiveToolChange?.(null);
        if (controlledTool === undefined) setLocalTool(null);
      }}
      onIndicatorToggle={handleIndicatorToggle}
      onMaximize={toggleMaximize}
      onTimeframeChange={setUserTimeframe}
      onToolClick={handleToolClick}
      onPointerDown={() => {
        claimChartDrawingHotkeyFocus(drawingHotkeyOwnerRef.current);
        onFocusPane?.();
      }}
      onPointerEnter={() => claimChartDrawingHotkeyFocus(drawingHotkeyOwnerRef.current)}
      loading={false}
      error={null}
      emptyText={indicatorBars.length === 0 ? 'No closed bars' : null}
      historyErrorTs={null}
      paneOverlay={renderPaneOverlay?.({
        symbol,
        timeframe,
        chart: chartApi,
        candleSeriesRef,
        containerRef,
        barsRevision,
      }) ?? null}
      chartApi={chartApi}
      candleSeriesRef={candleSeriesRef}
      vwapSource={vwapSource}
      liveTipTime={null}
      onOscDragStart={onOscDragStart}
      resetOscSplit={resetOscSplit}
      oscillatorEnabled={oscillatorEnabled}
      variant={variant}
    />
  );

  return (
    <ChartPortalFrame slotRef={slotRef} host={host} portalMaximized={portalMaximized} chartHeight={chartHeight}>
      {card}
    </ChartPortalFrame>
  );
}
