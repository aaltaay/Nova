/** ADR 005 — chart feature slice public types. */
import type { ReactNode, RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';

export interface ChartTradeUpdate {
  price: number;
  timestamp: string | null;
  /** When set, live merges must ignore trades for a different symbol. */
  symbol?: string | null;
  /** `snapshot` = a Level 1 last, not a print: never merged into a candle. */
  source?: 'stream' | 'snapshot' | 'sim';
  /**
   * The day's running volume IBKR reported with this update. The forming
   * candle's volume is what it grew by while the bar was open.
   */
  dayVolume?: number | null;
}

/**
 * What a page may draw inside one chart pane (the Trader tab's stock read, ADR 036): the pane's
 * chart, its candle series and body, and the bars revision that bumps when its bars reload.
 */
export interface ChartPaneOverlayProps {
  symbol: string;
  timeframe: string;
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
}

export type RenderPaneOverlay = (props: ChartPaneOverlayProps) => ReactNode;
