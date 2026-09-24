/**
 * Position tag + right-click menu hosted on one pane's `.chart-body`, and
 * whatever the page draws there (`renderOverlay`: the Trader tab's stock read).
 * Extracted from TickerChart so that file can stay under the component limit.
 */
import type { RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { ChartIndicatorId } from '../constants';
import { ChartContextMenuHost } from './ChartContextMenuHost';
import { ChartPositionTagHost } from './ChartPositionTag';
import type { RenderPaneOverlay } from './types';

export function ChartPaneOverlays(props: {
  symbol: string;
  timeframe: string;
  barCount: number;
  barsRevision: number;
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  activeTool: string | null;
  onToolClick: (toolId: string) => void;
  enabledIndicators: ChartIndicatorId[];
  onIndicatorToggle: (id: ChartIndicatorId) => void;
  renderOverlay?: RenderPaneOverlay;
}) {
  return (
    <>
      <ChartPositionTagHost
        symbol={props.symbol}
        chart={props.chart}
        candleSeriesRef={props.candleSeriesRef}
        containerRef={props.containerRef}
        barsRevision={props.barsRevision}
      />
      <ChartContextMenuHost
        symbol={props.symbol}
        timeframe={props.timeframe}
        barCount={props.barCount}
        chart={props.chart}
        candleSeriesRef={props.candleSeriesRef}
        containerRef={props.containerRef}
        activeTool={props.activeTool}
        onToolClick={props.onToolClick}
        enabledIndicators={props.enabledIndicators}
        onIndicatorToggle={props.onIndicatorToggle}
      />
      {props.renderOverlay?.({
        symbol: props.symbol,
        timeframe: props.timeframe,
        chart: props.chart,
        candleSeriesRef: props.candleSeriesRef,
        containerRef: props.containerRef,
        barsRevision: props.barsRevision,
      })}
    </>
  );
}
