/**
 * Earnings and split marks on a daily, weekly or monthly pane (operator ask, 2026-10-12: "i want the earnings
 * to show on the daily charts and same thing for reverse splits or splits"). E rings mark the day results came
 * out, M rings the day a split took effect, along the bottom of the price pane (`ChartEventsPrimitive`); the
 * pointer on one opens its card -- the date, the period and the report's figures, or the split's ratio, and
 * where each came from (`chartEvents.eventCard`). A source that could not be read is said in a chip on the
 * pane, never shown as "no events". Intraday panes draw none.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import type { IChartApi, ISeriesApi, MouseEventParams, Time } from 'lightweight-charts';
import { isDailyTimeframe } from '../tickerChartData';
import { chartContextMenuPortalTarget } from './chartContextMenuPortal';
import {
  CHART_EVENT_CARD_GAP_PX,
  CHART_EVENT_CARD_W_PX,
  CHART_EVENT_COLORS,
  CHART_EVENT_LETTERS,
} from './chartEventConstants';
import { eventCard, placeEvents, seriesDay, type ChartEvent, type EventCard } from './chartEvents';
import { CHART_EVENT_HOVER_PREFIX, ChartEventsPrimitive, type EventMark } from './ChartEventsPrimitive';
import { CANDLE_HOVER_EDGE_PX } from './candleHoverConstants';
import { useChartEvents } from './useChartEvents';

interface Props {
  symbol: string;
  timeframe: string;
  chart: IChartApi | null;
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>;
  containerRef: RefObject<HTMLElement | null>;
  barsRevision: number;
}

interface Hover {
  id: string;
  x: number;
  y: number;
}

function seriesTimes(series: ISeriesApi<'Candlestick'> | null): Time[] {
  try {
    return series ? series.data().map((d) => d.time) : [];
  } catch {
    return []; // maintainer: allow-swallow the series was disposed with its chart; no candles, no marks
  }
}

export function ChartEventMarkers({ symbol, timeframe, chart, candleSeriesRef, containerRef, barsRevision }: Props) {
  const daily = isDailyTimeframe(timeframe);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the series' candles change with barsRevision
  const times = useMemo(() => (daily ? seriesTimes(candleSeriesRef.current) : []), [daily, candleSeriesRef, barsRevision]);
  const newest = times.length > 0 ? seriesDay(times[times.length - 1]) : null;
  const read = useChartEvents(daily ? symbol : null, newest);
  const placed = useMemo(() => placeEvents(read.events, times, timeframe), [read.events, times, timeframe]);

  const primitiveRef = useRef<ChartEventsPrimitive | null>(null);
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!chart || !series || !daily) return;
    const primitive = new ChartEventsPrimitive();
    series.attachPrimitive(primitive);
    primitiveRef.current = primitive;
    return () => {
      try {
        series.detachPrimitive(primitive);
      } catch {
        // maintainer: allow-swallow the chart was disposed with the series; nothing is left to detach
      }
      if (primitiveRef.current === primitive) primitiveRef.current = null;
    };
  }, [chart, candleSeriesRef, daily]);

  useEffect(() => {
    const marks: EventMark[] = placed.map(({ event, time }) => ({
      id: event.id, time, letter: CHART_EVENT_LETTERS[event.kind], color: CHART_EVENT_COLORS[event.kind],
    }));
    primitiveRef.current?.setMarks(marks);
  }, [placed, chart, daily]);

  const hover = useEventHover(daily ? chart : null);
  const shown = hover ? placed.find((p) => p.event.id === hover.id)?.event ?? null : null;
  const failed = read.notes.length > 0 && !read.busy;

  if (!daily) return null;
  return (
    <>
      {failed && (
        <div className="chart-events-note" title={read.notes.join('\n')} data-testid="chart-events-note">
          E / M: {read.notes.length === 1 ? 'a source was not read' : `${read.notes.length} sources were not read`}
        </div>
      )}
      {shown && hover && (
        <EventCardView card={eventCard(shown, read.coverage)} event={shown} hover={hover} containerRef={containerRef} />
      )}
    </>
  );
}

/** The mark under the pointer on `chart`, with the pointer's place; null over anything else. */
function useEventHover(chart: IChartApi | null): Hover | null {
  const [hover, setHover] = useState<Hover | null>(null);
  useEffect(() => {
    if (!chart) return;
    const onMove = (p: MouseEventParams<Time>) => {
      const raw = p.hoveredObjectId == null ? '' : String(p.hoveredObjectId);
      const point = p.point;
      setHover((prev) => {
        if (!raw.startsWith(CHART_EVENT_HOVER_PREFIX) || !point) return prev === null ? prev : null;
        const id = raw.slice(CHART_EVENT_HOVER_PREFIX.length);
        if (prev && prev.id === id && prev.x === point.x && prev.y === point.y) return prev;
        return { id, x: point.x, y: point.y };
      });
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      try {
        chart.unsubscribeCrosshairMove(onMove);
      } catch {
        // maintainer: allow-swallow the chart was already disposed, so it holds no subscription
      }
      setHover(null);
    };
  }, [chart]);
  return hover;
}

const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), Math.max(low, high));

/** The mark's card above the pointer, floating over the desk as the candle card does. */
function EventCardView({ card, event, hover, containerRef }: {
  card: EventCard;
  event: ChartEvent;
  hover: Hover;
  containerRef: RefObject<HTMLElement | null>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [cardH, setCardH] = useState(0);
  useLayoutEffect(() => {
    const h = ref.current?.offsetHeight ?? 0;
    if (h !== cardH) setCardH(h);
  }, [card, cardH]);
  const pane = containerRef.current;
  const target = chartContextMenuPortalTarget(pane);
  if (!pane || !target) return null;
  const box = pane.getBoundingClientRect();
  const flip = hover.x + CHART_EVENT_CARD_GAP_PX + CHART_EVENT_CARD_W_PX > box.width;
  const paneLeft = flip ? hover.x - CHART_EVENT_CARD_GAP_PX - CHART_EVENT_CARD_W_PX : hover.x + CHART_EVENT_CARD_GAP_PX;
  const left = clamp(box.left + paneLeft, CANDLE_HOVER_EDGE_PX, window.innerWidth - CHART_EVENT_CARD_W_PX - CANDLE_HOVER_EDGE_PX);
  const top = clamp(box.top + hover.y - CHART_EVENT_CARD_GAP_PX - cardH, CANDLE_HOVER_EDGE_PX,
    window.innerHeight - cardH - CANDLE_HOVER_EDGE_PX);
  return createPortal(
    <div ref={ref} className="candle-tip chart-event-tip" style={{ left, top, width: CHART_EVENT_CARD_W_PX }}
      role="tooltip" data-testid="chart-event-tip" data-event-kind={event.kind}>
      <div className="candle-tip__top">
        <i className={`chart-event-tip__dot chart-event-tip__dot--${card.color}`} aria-hidden="true">
          {CHART_EVENT_LETTERS[event.kind]}
        </i>
        <span>{card.title}</span>
      </div>
      <div className="candle-tip__section">
        {card.rows.map((row) => (
          <div key={row.label} className={`candle-tip__row${row.warn ? ' chart-event-tip__warn' : ''}`}>
            <span>{row.label}</span>
            <span>
              {row.value}
              {row.note && <em className="chart-event-tip__note">{row.note}</em>}
            </span>
          </div>
        ))}
      </div>
      {card.quote && <div className="chart-event-tip__quote">“{card.quote}”</div>}
      <div className="chart-event-tip__source">{card.source}</div>
      {card.coverage && <div className="chart-event-tip__source">{card.coverage}</div>}
    </div>,
    target,
  );
}
