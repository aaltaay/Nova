/**
 * A setup's story under the pointer on the 1-minute pane (ADR 036 amendment, operator ask 2026-09-29).
 * The chart reports which box the pointer is over (`SetupShapesPrimitive.hitTest`); this names it -- a
 * live lane's state and reason, or a past setup's end, the rule it broke and what price did next -- in a
 * card beside the pointer. The card takes no pointer events, so the chart keeps every gesture.
 */
import { useEffect, useState, type RefObject } from 'react';
import type { IChartApi, MouseEventParams, Time } from 'lightweight-charts';
import { laneHoverId } from './chartShapes';
import { laneStory, pastStory, type Episode } from './pastSetups';
import { pastHoverId } from './pastShapes';
import type { StockRead } from './types';

export interface ShapeHover {
  id: string;
  x: number;
  y: number;
  /** The pane's size when the pointer got there, so the card stays inside it; 0 when unknown. */
  width: number;
  height: number;
}

export interface ShapeStory {
  title: string;
  lines: string[];
}

/** The card's width, and the gap between it and the pointer. */
const TIP_W = 300;
const TIP_GAP = 14;

/** The box under the pointer on `chart`, with the pointer's place; null over anything else. */
export function useShapeHover(
  chart: IChartApi | null,
  enabled: boolean,
  containerRef: RefObject<HTMLElement | null>,
): ShapeHover | null {
  const [hover, setHover] = useState<ShapeHover | null>(null);
  useEffect(() => {
    if (!chart || !enabled) return;
    const onMove = (p: MouseEventParams<Time>) => {
      const id = typeof p.hoveredObjectId === 'string' ? p.hoveredObjectId : null;
      const point = p.point;
      const box = containerRef.current;
      setHover(prev => {
        if (!id || !point) return prev === null ? prev : null;
        if (prev && prev.id === id && prev.x === point.x && prev.y === point.y) return prev;
        return { id, x: point.x, y: point.y, width: box?.clientWidth ?? 0, height: box?.clientHeight ?? 0 };
      });
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      try {
        chart.unsubscribeCrosshairMove(onMove);
      } catch {
        /* the chart is gone */
      }
      setHover(null);
    };
  }, [chart, enabled, containerRef]);
  return enabled ? hover : null;
}

/** The story of the box `id` names: a live lane's, or a past setup's. */
export function shapeStory(id: string, read: StockRead, past: Episode[] | null): ShapeStory | null {
  if (id.startsWith('lane:')) {
    const lane = read.setups.find(l => laneHoverId(l.setup_type) === id);
    return lane ? laneStory(lane) : null;
  }
  const ep = past?.find(e => pastHoverId(e) === id);
  return ep ? pastStory(ep) : null;
}

export function ShapeTip({ story, hover }: { story: ShapeStory; hover: ShapeHover }) {
  const { x, y, width, height } = hover;
  const left = width > 0 && x + TIP_GAP + TIP_W > width ? Math.max(4, x - TIP_GAP - TIP_W) : x + TIP_GAP;
  const below = height <= 0 || y < height * 0.55;
  const style = below ? { left, top: y + TIP_GAP } : { left, bottom: height - y + TIP_GAP };
  return (
    <div className="sr-shape-tip" style={style} role="tooltip" data-testid="stock-read-shape-tip">
      <div className="sr-shape-tip__title">{story.title}</div>
      {story.lines.map((line, i) => (
        <div key={i} className="sr-shape-tip__line">{line}</div>
      ))}
    </div>
  );
}
