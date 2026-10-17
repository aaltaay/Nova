/** The volume profile inside a Trader chart pane: drawn on the 5-minute pane only (decision D4), nothing elsewhere. */
import type { ChartPaneOverlayProps } from '../chart';
import { useProfileShown } from './volumeProfilePrefs';
import { useVolumeProfile } from './useVolumeProfile';
import { VP_TIMEFRAME } from './volumeProfileConstants';

export function VolumeProfileChartLayer({ symbol, timeframe, chart, candleSeriesRef, containerRef, barsRevision }: ChartPaneOverlayProps) {
  const shown = useProfileShown();
  useVolumeProfile({
    symbol,
    chart,
    series: chart ? candleSeriesRef.current : null,
    containerRef,
    barsRevision,
    enabled: shown && timeframe === VP_TIMEFRAME,
  });
  return null;
}
