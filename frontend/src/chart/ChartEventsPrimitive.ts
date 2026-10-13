/**
 * The earnings and split marks on a daily pane (operator ask, 2026-10-12): a ring with a letter -- E for
 * earnings, M for a split -- along the bottom of the price pane under the candle it belongs to, a second
 * mark on one candle stacked above the first. The pane reports a mark under the pointer as hovered
 * (`hitTest`, id `chart-event:<event id>`) for its card, and the candle card steps aside there as it does for
 * any mark (`useCandleHover`). Display only; asks for a redraw only when its marks change.
 */
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type {
  AutoscaleInfo,
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  PrimitiveHoveredItem,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';
import {
  CHART_EVENT_BOTTOM_GAP_PX,
  CHART_EVENT_FILL,
  CHART_EVENT_FONT_PX,
  CHART_EVENT_HIT_SLACK_PX,
  CHART_EVENT_RADIUS_PX,
  CHART_EVENT_RING_PX,
  CHART_EVENT_STACK_GAP_PX,
} from './chartEventConstants';

/** What a mark under the pointer is reported as. */
export const CHART_EVENT_HOVER_PREFIX = 'chart-event:';

export interface EventMark {
  id: string;
  time: Time;
  letter: string;
  color: string;
}

export interface EventMarkPx {
  id: string;
  x: number;
  y: number;
  letter: string;
  color: string;
}

/** Pixels for each mark whose candle is on the time scale, in a pane `height` pixels tall. */
export function layoutEventMarks(
  marks: readonly EventMark[],
  x: (mark: EventMark) => number | null,
  height: number,
): EventMarkPx[] {
  const stacked = new Map<number, number>();
  const out: EventMarkPx[] = [];
  for (const m of marks) {
    const px = x(m);
    if (px == null) continue;
    const key = Math.round(px);
    const level = stacked.get(key) ?? 0;
    stacked.set(key, level + 1);
    const y = height - CHART_EVENT_BOTTOM_GAP_PX - CHART_EVENT_RADIUS_PX
      - level * (2 * CHART_EVENT_RADIUS_PX + CHART_EVENT_STACK_GAP_PX);
    out.push({ id: m.id, x: px, y, letter: m.letter, color: m.color });
  }
  return out;
}

/** The mark under (`x`, `y`), the top one when two touch; null over none. */
export function markAt(px: readonly EventMarkPx[], x: number, y: number): EventMarkPx | null {
  for (let i = px.length - 1; i >= 0; i -= 1) {
    if (Math.hypot(x - px[i].x, y - px[i].y) <= CHART_EVENT_RADIUS_PX + CHART_EVENT_HIT_SLACK_PX) return px[i];
  }
  return null;
}

class EventMarksRenderer implements IPrimitivePaneRenderer {
  private readonly source: ChartEventsPrimitive;

  constructor(source: ChartEventsPrimitive) {
    this.source = source;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const px = this.source.layout(mediaSize.height);
      if (px.length === 0) return;
      ctx.save();
      ctx.lineWidth = CHART_EVENT_RING_PX;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.font = `700 ${CHART_EVENT_FONT_PX}px ${this.source.fontFamily}`;
      for (const m of px) {
        ctx.beginPath();
        ctx.arc(m.x, m.y, CHART_EVENT_RADIUS_PX, 0, Math.PI * 2);
        ctx.fillStyle = CHART_EVENT_FILL;
        ctx.fill();
        ctx.strokeStyle = m.color;
        ctx.stroke();
        ctx.fillStyle = m.color;
        ctx.fillText(m.letter, m.x, m.y + 0.5);
      }
      ctx.restore();
    });
  }
}

class EventMarksView implements IPrimitivePaneView {
  private readonly source: ChartEventsPrimitive;

  constructor(source: ChartEventsPrimitive) {
    this.source = source;
  }

  zOrder(): PrimitivePaneViewZOrder {
    return 'top';
  }

  renderer(): IPrimitivePaneRenderer {
    return new EventMarksRenderer(this.source);
  }
}

export class ChartEventsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private requestUpdate: (() => void) | null = null;
  private marks: readonly EventMark[] = [];
  private key = '';
  private xs = new Map<string, number | null>();
  private readonly views = [new EventMarksView(this)];
  /** Where each mark was last drawn, for `hitTest`. */
  px: EventMarkPx[] = [];
  fontFamily = 'sans-serif';

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = param.chart;
    this.requestUpdate = param.requestUpdate;
    if (this.marks.length > 0) this.requestUpdate();
  }

  detached(): void {
    this.chart = null;
    this.requestUpdate = null;
    this.px = [];
  }

  /** New marks redraw the pane; the same marks again do nothing. */
  setMarks(marks: readonly EventMark[]): void {
    const key = marks.map((m) => `${m.id}:${String(m.time)}:${m.letter}:${m.color}`).join('|');
    if (key === this.key) return;
    this.key = key;
    this.marks = marks;
    this.requestUpdate?.();
  }

  updateAllViews(): void {
    const chart = this.chart;
    this.xs = new Map();
    if (!chart || this.marks.length === 0) return;
    const scale = chart.timeScale();
    this.fontFamily = chart.options().layout.fontFamily;
    for (const m of this.marks) this.xs.set(m.id, scale.timeToCoordinate(m.time));
  }

  /** The marks' pixels in a pane this tall, kept for `hitTest`. */
  layout(height: number): EventMarkPx[] {
    this.px = layoutEventMarks(this.marks, (mark) => this.xs.get(mark.id) ?? null, height);
    return this.px;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Room under the lowest candle for the row of marks, so no candle, line or level label sits on them. */
  autoscaleInfo(): AutoscaleInfo | null {
    if (this.marks.length === 0) return null;
    const perCandle = new Map<string, number>();
    for (const m of this.marks) perCandle.set(String(m.time), (perCandle.get(String(m.time)) ?? 0) + 1);
    const rows = Math.max(...perCandle.values());
    const below = CHART_EVENT_BOTTOM_GAP_PX + rows * 2 * CHART_EVENT_RADIUS_PX + (rows - 1) * CHART_EVENT_STACK_GAP_PX
      + CHART_EVENT_BOTTOM_GAP_PX;
    return { priceRange: null, margins: { above: 0, below } };
  }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const hit = markAt(this.px, x, y);
    return hit ? { externalId: `${CHART_EVENT_HOVER_PREFIX}${hit.id}`, zOrder: 'top', cursorStyle: 'pointer' } : null;
  }
}
