/**
 * A setup's story under the pointer on the 1-minute pane (ADR 036 amendment, operator ask 2026-09-29), and
 * a level's on the 5-minute and Full Day panes (2026-09-30). The chart reports which box, label or axis
 * tick the pointer is over (`SetupShapesPrimitive.hitTest`); this names it -- a live lane's state and
 * reason, a past setup's end, the rule it broke and what price did next, or what holds a level and what the
 * level study measured -- in a card beside the pointer. The card takes no pointer events, so the chart
 * keeps every gesture. Over a setup's box, a candle the pointer rests on wins (operator report 2026-10-12):
 * the box's card steps aside while the candle's card is open, and shows again once it closes.
 */
import { useEffect, useState, type RefObject } from 'react';
import type { IChartApi, MouseEventParams, Time } from 'lightweight-charts';
import { hoverTarget, useCandleCardOpen } from '../chart';
import { laneHoverId } from './chartShapes';
import { fiveMinuteLanes, lane5HoverId, past5HoverId } from './fiveMinuteShapes';
import { FLAT_TOP_5M } from './flatTopShapes';
import { foldedStory } from './levelFold';
import { levelStory } from './levelZone';
import { laneStory, pastStory, type Episode } from './pastSetups';
import { pastHoverId } from './pastShapes';
import { trendStory } from './trendLines';
import type { StockRead } from './types';

export interface ShapeHover {
  id: string;
  /** Over the drawing's area (a setup's box), where a candle the pointer rests on wins. */
  area: boolean;
  x: number;
  y: number;
  /** The pane's size when the pointer got there, so the card stays inside it; 0 when unknown. */
  width: number;
  height: number;
}

export interface ShapeStory {
  title: string;
  lines: string[];
  /** A short line under the title ("Resistance · $1.06 above the price"). */
  subtitle?: string;
  /** The drawing's colour, shown beside the title. */
  color?: string;
  /** Headed lists, after the lines. */
  sections?: { head: string; items: string[] }[];
}

/** The card's width, and the gap between it and the pointer. */
const TIP_W = 300;
const TIP_GAP = 14;

/** The box under the pointer on `chart`, with the pointer's place; null over anything else, and over a box's
 * area while the candle card is open there. */
export function useShapeHover(
  chart: IChartApi | null,
  enabled: boolean,
  containerRef: RefObject<HTMLElement | null>,
): ShapeHover | null {
  const [hover, setHover] = useState<ShapeHover | null>(null);
  const candleCardOpen = useCandleCardOpen(enabled ? chart : null);
  useEffect(() => {
    if (!chart || !enabled) return;
    const onMove = (p: MouseEventParams<Time>) => {
      const target = hoverTarget(p.hoveredObjectId);
      const point = p.point;
      const box = containerRef.current;
      setHover(prev => {
        if (!target?.id || !point) return prev === null ? prev : null;
        const { id, area } = target;
        if (prev && prev.id === id && prev.area === area && prev.x === point.x && prev.y === point.y) return prev;
        return { id, area, x: point.x, y: point.y, width: box?.clientWidth ?? 0, height: box?.clientHeight ?? 0 };
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
  if (!enabled || !hover) return null;
  return hover.area && candleCardOpen ? null : hover;
}

/** The story of the box `id` names: a live lane's, a past setup's, a level's (its label or axis tick) or a trend
 * line's --
 * a 5-minute lane's or setup's (`lane5:` / `past5:`) named as one; a label that took others' names, each of theirs
 * (`levelFold.foldedStory`). */
export function shapeStory(id: string, read: StockRead, past: Episode[] | null,
  past5: Episode[] | null = null): ShapeStory | null {
  const folded = foldedStory(id, part => shapeStory(part, read, past, past5));
  if (folded) return folded;
  if (id.startsWith('level:')) return levelStory(id, read);
  if (id.startsWith('trend:')) return trendStory(id, read);
  const five = (s: ShapeStory | null) => (s ? { ...s, title: `5-minute · ${s.title}` } : null);
  // The 5-minute flat top names itself; a built-in 5-minute lane's story is the 1-minute setup's, named so.
  const named = (type: string, s: ShapeStory | null) => (type === FLAT_TOP_5M ? s : five(s));
  if (id.startsWith('lane5:')) {
    const lane = fiveMinuteLanes(read).find(l => lane5HoverId(l.setup_type) === id);
    return lane ? named(lane.setup_type, laneStory(lane)) : null;
  }
  if (id.startsWith('past5:')) {
    const ep = past5?.find(e => past5HoverId(e) === id);
    return ep ? named(ep.setup_type, pastStory(ep)) : null;
  }
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
      <div className="sr-shape-tip__title">
        {story.color && <i className="sr-shape-tip__swatch" style={{ background: story.color }} aria-hidden="true" />}
        {story.title}
      </div>
      {story.subtitle && <div className="sr-shape-tip__subtitle">{story.subtitle}</div>}
      {story.lines.map((line, i) => (
        <div key={i} className="sr-shape-tip__line">{line}</div>
      ))}
      {story.sections?.map((sec, i) => (
        <div key={`${i}:${sec.head}`} className="sr-shape-tip__section">
          <div className="sr-shape-tip__head">{sec.head}</div>
          <ul className="sr-shape-tip__list">
            {sec.items.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}
