/**
 * What the stock read adds to a pane's scene besides `paneDraw` (operator report 2026-09-30: "everything is
 * getting on top of each other in the charts!"): the words for the edge column -- the plan's lines' names (the
 * lines keep their prices on the axis) -- the Full Day pane's +40% runs as marks that make room for each other,
 * and the price axis's width, where the legend ends.
 */
import { useEffect, useState } from 'react';
import type { Time } from 'lightweight-charts';
import {
  EDGE_PRIORITY,
  nearestSeriesTime,
  toCanonicalTime,
  type ChartPaneOverlayProps,
  type SeriesTimeIndex,
} from '../chart';
import type { PriceLineSpec } from './chartShapes';
import type { SceneMark, SceneWord } from './sceneTypes';
import type { RunDay } from './types';

/** Every +40% run on its day's candle: an arrow over the high and a label; where labels crowd, today's and
 * then the biggest runs keep theirs (each arrow stays). */
export function runMarks(runs: RunDay[], index: SeriesTimeIndex): SceneMark[] {
  const out: SceneMark[] = [];
  for (const r of runs) {
    const target = toCanonicalTime(r.date as Time);
    const t = nearestSeriesTime(index, target);
    if (t === null || Math.abs(toCanonicalTime(t) - target) > 86_400) continue;
    out.push({
      t,
      price: r.high,
      color: r.today ? '#30d158' : '#f59e0b',
      label: `${r.today ? 'today ' : ''}+${Math.round(r.run_pct * 100)}%`,
      rank: r.today ? Number.MAX_SAFE_INTEGER : r.run_pct,
    });
  }
  return out;
}

/** The plan's price lines' names go to the edge column; the lines keep their axis labels (the prices). */
export function lineWords(lines: PriceLineSpec[]): SceneWord[] {
  return lines.filter(l => l.axisLabel && l.title).map(l => ({
    id: `line:${l.id}`, text: l.title, color: l.color, priority: EDGE_PRIORITY.planLine, price: l.price, series: null,
    valueWhenOff: true,
  }));
}

/** The price axis's width, kept current: the legend ends where the axis begins. */
export function usePriceScaleWidth(chart: ChartPaneOverlayProps['chart'], containerRef: ChartPaneOverlayProps['containerRef'],
  barsRevision: number, active: boolean): number {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!chart || !active) return;
    const read = () => {
      try {
        const w = chart.priceScale('right').width();
        setWidth(prev => (prev === w ? prev : w));
      } catch {
        /* the chart is gone */
      }
    };
    read();
    const frame = requestAnimationFrame(read); // the axis sizes itself on its first paint
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(read);
    if (ro && containerRef.current) ro.observe(containerRef.current);
    const ts = chart.timeScale();
    try {
      ts.subscribeVisibleLogicalRangeChange(read);
    } catch {
      /* jsdom / a detached chart */
    }
    return () => {
      cancelAnimationFrame(frame);
      ro?.disconnect();
      try {
        ts.unsubscribeVisibleLogicalRangeChange(read);
      } catch {
        /* already gone */
      }
    };
  }, [chart, containerRef, barsRevision, active]);
  return width;
}
