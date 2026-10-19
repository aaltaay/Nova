/** Shared card chrome for the live pane and the recorded review pane. */

import type { CSSProperties, ReactNode, RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  CHART_OSCILLATOR_IDS,
  type ChartIndicatorId,
  type ChartOscillatorId,
} from '../constants';
import { ResizeHandle } from '../components/ResizeHandle';
import { TickerChartControls } from '../components/TickerChartControls';
import { TickerChartOverlays } from '../components/TickerChartOverlays';
import { TickerChartOscillatorPanes } from '../components/TickerChartOscillatorPanes';
import type { DrawingSelectionState } from './chartDrawingColor';
import { CandleHoverTip } from './CandleHoverTip';
import { ChartFillingOverlay, chartFillingHint } from './ChartFillingStatus';
import type { IndicatorBar } from '../chartIndicators';
import { formatCoverageClockEt } from '../tickerChartData';
import { SAMPLE_CHART_NO_BARS, SAMPLE_NETWORK_REFUSAL } from '../sample_data/sampleCopy';
import type { VwapSource } from './useVwapSourceBars';

export function TickerChartCard({
  cardRef,
  containerRef,
  cardClass,
  symbol,
  timeframe,
  indicatorBars,
  barsRevision,
  filling,
  focused,
  positionAvg,
  positionQty,
  gridOscillators,
  pricePct,
  activeTool,
  enabledIndicators,
  lockTimeframe,
  headerMaximized,
  subtitle,
  title,
  usingMock,
  compactChrome,
  keepCompactWhenMaximized,
  useFullscreenExpand,
  coverageAsOf,
  historyError,
  selection,
  onClearAll,
  onColorChange,
  onIndicatorToggle,
  onMaximize,
  onTimeframeChange,
  onToolClick,
  onPointerDown,
  onPointerEnter,
  loading,
  error,
  emptyText,
  historyErrorTs,
  paneOverlay,
  chartApi,
  candleSeriesRef,
  volSeriesRef,
  vwapSource,
  accountOverlay,
  liveTipTime,
  onOscDragStart,
  resetOscSplit,
  oscillatorEnabled,
  variant,
}: {
  cardRef: RefObject<HTMLDivElement | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  cardClass: string;
  symbol: string;
  timeframe: string;
  indicatorBars: IndicatorBar[];
  barsRevision: number;
  filling: boolean;
  focused: boolean;
  positionAvg?: string;
  positionQty?: string;
  gridOscillators: boolean;
  pricePct: number;
  activeTool: string | null;
  enabledIndicators: ChartIndicatorId[];
  lockTimeframe: boolean;
  headerMaximized: boolean;
  subtitle?: string;
  title?: string;
  usingMock: boolean;
  compactChrome: boolean;
  keepCompactWhenMaximized: boolean;
  useFullscreenExpand: boolean;
  coverageAsOf: string | null;
  historyError: string | null;
  selection: DrawingSelectionState | null;
  onClearAll: () => void;
  onColorChange?: (color: string) => void;
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  onMaximize: () => void;
  onTimeframeChange: (timeframe: string) => void;
  onToolClick: (toolId: string) => void;
  onPointerDown: () => void;
  onPointerEnter: () => void;
  loading: boolean;
  error: string | null;
  emptyText: string | null;
  historyErrorTs: number | null;
  paneOverlay: ReactNode;
  chartApi: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  volSeriesRef: RefObject<ISeriesApi<'Histogram'> | null>;
  vwapSource: VwapSource;
  accountOverlay: boolean;
  liveTipTime: number | null;
  onOscDragStart: (event: React.PointerEvent) => void;
  resetOscSplit: () => void;
  oscillatorEnabled: ChartOscillatorId[];
  variant: 'panel' | 'page' | 'grid';
}) {
  const coverageClock = formatCoverageClockEt(coverageAsOf);
  return (
    <div
      ref={cardRef}
      className={cardClass}
      data-testid={`ticker-chart-${timeframe}`}
      data-bar-count={indicatorBars.length}
      data-filling={filling ? '1' : '0'}
      data-focused={focused ? '1' : '0'}
      data-position-avg={positionAvg}
      data-position-qty={positionQty}
      style={
        gridOscillators
          ? ({ ['--chart-osc-pct' as string]: `${100 - pricePct}%` } as CSSProperties)
          : undefined
      }
      onPointerDown={onPointerDown}
      onPointerEnter={onPointerEnter}
    >
      <TickerChartControls
        activeTool={activeTool}
        enabledIndicators={enabledIndicators}
        lockTimeframe={lockTimeframe}
        maximized={headerMaximized}
        subtitle={subtitle}
        timeframe={timeframe}
        title={title}
        usingMock={usingMock}
        compact={compactChrome}
        keepCompactWhenMaximized={keepCompactWhenMaximized}
        useFullscreenExpand={useFullscreenExpand}
        fillingHint={
          filling && indicatorBars.length > 0 ? chartFillingHint(coverageClock, historyError) : null
        }
        selection={selection}
        onClearAll={onClearAll}
        onColorChange={onColorChange}
        onIndicatorToggle={onIndicatorToggle}
        onMaximize={onMaximize}
        onTimeframeChange={onTimeframeChange}
        onToolClick={onToolClick}
      />

      <div className="chart-body" ref={containerRef}>
        {loading && indicatorBars.length === 0 && (
          <div className="chart-overlay">Loading…</div>
        )}
        {!loading && filling && indicatorBars.length === 0 && !error && (
          <ChartFillingOverlay lastError={historyError} lastErrorTs={historyErrorTs} />
        )}
        {!loading && error && indicatorBars.length === 0 && (
          error === SAMPLE_NETWORK_REFUSAL ? (
            <div className="chart-overlay chart-overlay--empty" data-testid="chart-empty">{SAMPLE_CHART_NO_BARS}</div>
          ) : (
            <div className="chart-overlay chart-overlay--error">{error}</div>
          )
        )}
        {!loading && !error && emptyText && indicatorBars.length === 0 && (
          <div className="chart-overlay chart-overlay--empty" data-testid="chart-empty">{emptyText}</div>
        )}
        {paneOverlay}
        <CandleHoverTip chart={chartApi} candleSeriesRef={candleSeriesRef} volSeriesRef={volSeriesRef}
          containerRef={containerRef} symbol={symbol} timeframe={timeframe} paneBars={indicatorBars} vwapSource={vwapSource} />
      </div>
      <TickerChartOverlays
        chart={chartApi}
        candleSeriesRef={candleSeriesRef}
        symbol={symbol}
        bars={indicatorBars}
        barsRevision={barsRevision}
        enabled={enabledIndicators}
        timeframe={timeframe}
        vwapSourceBars={vwapSource.bars}
        vwapSourceRevision={vwapSource.revision}
        vwapCoversOpen={vwapSource.coversOpen}
        liveTipTime={liveTipTime}
        accountOverlay={accountOverlay}
      />
      {gridOscillators && (
        <ResizeHandle
          orientation="horizontal"
          onPointerDown={onOscDragStart}
          onDoubleClick={resetOscSplit}
          label="Resize indicator pane"
        />
      )}
      {oscillatorEnabled.length > 0 && (
        <TickerChartOscillatorPanes
          parentChart={chartApi}
          bars={indicatorBars}
          barsRevision={barsRevision}
          enabled={oscillatorEnabled}
          onClose={variant === 'grid' ? onIndicatorToggle : undefined}
        />
      )}
    </div>
  );
}

export function oscillatorIds(enabled: ChartIndicatorId[]): ChartOscillatorId[] {
  return enabled.filter((id): id is ChartOscillatorId =>
    (CHART_OSCILLATOR_IDS as readonly ChartOscillatorId[]).includes(id as ChartOscillatorId),
  );
}
