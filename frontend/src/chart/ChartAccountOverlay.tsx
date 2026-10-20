/** Account avg-cost line. The live pane mounts this. /review never imports it. */

import type { RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { IndicatorBar } from '../chartIndicators';
import { useChartPositionOverlay } from './useChartPositionOverlay';

export function ChartAccountOverlay(props: {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  symbol: string;
  timeframe: string;
  bars: IndicatorBar[];
  barsRevision: number;
}) {
  useChartPositionOverlay(props);
  return null;
}
