import { useEffect, useState, type RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import {
  positionTagPlacement,
  type PositionTagPlacement,
} from './positionTagLayout';

const EMPTY: PositionTagPlacement = { top: 0, right: 8, offScale: true };

export function useChartPositionTagLayout(input: {
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  avgCost: number;
  barsRevision: number;
}): PositionTagPlacement {
  const { chart, candleSeriesRef, containerRef, avgCost, barsRevision } = input;
  const [placement, setPlacement] = useState<PositionTagPlacement>(EMPTY);

  useEffect(() => {
    const container = containerRef.current;
    const series = candleSeriesRef.current;
    if (!container) return;

    const measure = () => {
      let y: number | null = null;
      let scaleW = 0;
      try {
        if (series) {
          const coord = series.priceToCoordinate(avgCost);
          y = coord == null ? null : coord;
        }
        if (chart) {
          scaleW = chart.priceScale('right').width();
        }
      } catch {
        y = null;
      }
      setPlacement(
        positionTagPlacement({
          y,
          paneHeight: container.clientHeight,
          priceScaleWidth: scaleW,
        }),
      );
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    const timeScale = chart?.timeScale();
    try {
      timeScale?.subscribeVisibleLogicalRangeChange(measure);
    } catch {
      /* jsdom / detached chart */
    }
    return () => {
      ro.disconnect();
      try {
        timeScale?.unsubscribeVisibleLogicalRangeChange(measure);
      } catch {
        /* already gone */
      }
    };
  }, [chart, candleSeriesRef, containerRef, avgCost, barsRevision]);

  return placement;
}
