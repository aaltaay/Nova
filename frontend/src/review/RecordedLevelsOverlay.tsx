/** Review levels on the desk pane. Uses the grid's existing overlay slot. */

import { useEffect, type ReactElement } from 'react';
import type { IPriceLine } from 'lightweight-charts';
import type { ChartPaneOverlayProps } from '../chart';
import { REVIEW_LEVEL_COLORS, levelLines, type ReviewLevels } from './reviewLevels';
import type { ReviewPayload } from './reviewFixture';

export function RecordedLevelsOverlay({
  chart,
  candleSeriesRef,
  timeframe,
  barsRevision,
  levels,
  setups,
}: ChartPaneOverlayProps & {
  levels: ReviewLevels;
  setups: ReviewPayload['setups'];
}) {
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series) return;
    const drawn: IPriceLine[] = [];
    for (const line of levelLines(levels)) {
      drawn.push(series.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 1,
        axisLabelVisible: true,
        title: line.title,
      }));
    }
    if (timeframe === '5Min' || timeframe === '1Min') {
      for (const setup of setups) {
        if (setup.kind !== 'flat_top') continue;
        drawn.push(series.createPriceLine({
          price: setup.price,
          color: REVIEW_LEVEL_COLORS.setup,
          lineWidth: 1,
          axisLabelVisible: true,
          title: setup.label,
        }));
      }
    }
    return () => {
      for (const line of drawn) series.removePriceLine(line);
    };
  }, [chart, candleSeriesRef, timeframe, barsRevision, levels, setups]);
  return null;
}

export function levelOverlay(
  levels: ReviewLevels,
  setups: ReviewPayload['setups'],
): (props: ChartPaneOverlayProps) => ReactElement {
  return function ReviewLevelSlot(props: ChartPaneOverlayProps) {
    return <RecordedLevelsOverlay {...props} levels={levels} setups={setups} />;
  };
}
