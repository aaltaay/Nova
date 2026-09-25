import { useEffect, useState, type RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import { CHART_POSITION_TAG_REMEASURE_MS } from './positionOverlayConstants';
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
      const next = positionTagPlacement({
        y,
        paneHeight: container.clientHeight,
        priceScaleWidth: scaleW,
      });
      setPlacement(prev => (prev.top === next.top && prev.right === next.right && prev.offScale === next.offScale
        ? prev
        : next));
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(container);
    const remeasure = window.setInterval(measure, CHART_POSITION_TAG_REMEASURE_MS);
    const timeScale = chart?.timeScale();
    try {
      timeScale?.subscribeVisibleLogicalRangeChange(measure);
    } catch {
      /* jsdom / detached chart */
    }
    return () => {
      window.clearInterval(remeasure);
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
