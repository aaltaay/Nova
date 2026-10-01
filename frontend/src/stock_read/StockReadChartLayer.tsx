/**
 * The stock read on one chart pane (ADR 036). The 1-minute pane gets the setups' shapes -- the day's
 * setups that ended faint under the live ones, each telling its story under the pointer -- the plan's
 * zones and lines, the day's levels, a legend of the lanes and the plan's badge -- with the trade's
 * track, the Who trades chip and the call's pin (ADR 037); the 5-minute pane carries today's level map and
 * the Full Day pane the daily one, each level's card under the pointer (ADR 036 amendment 2026-09-30);
 * the 5-minute and 10-second panes mirror the plan's levels as thin lines; the daily pane marks every
 * +40% run.
 * The pane's right edge is the scene's (operator report 2026-09-30: "everything is getting on top of each
 * other in the charts!"): it claims the edge (`claimEdge`), so the EMAs' and VWAP's tags, the plan's
 * ENTRY / STOP / TARGET and the position tag's room come to its one column with the levels' names instead of
 * being drawn over them, and the column starts under the corner chips.
 * Nothing is drawn while the desk replays another moment: the read is today's live stock.
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  type IPriceLine,
  type ISeriesApi,
  type LineStyle,
  type Time,
} from 'lightweight-charts';
import {
  buildSeriesTimeIndex,
  claimEdge,
  edgeContents,
  isFollowingRightEdge,
  nearestSeriesTime,
  subscribeEdge,
  toCanonicalTime,
  type ChartPaneOverlayProps,
  type SeriesTimeIndex,
} from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { ChartKey } from './ChartKey';
import { chartKey } from './paneKeyRows';
import { ChartLegend } from './ChartLegend';
import { laneStartSec, leadLane, paneDraw, paneKind, type PriceLineSpec } from './chartShapes';
import { levelNote } from './levelPicks';
import { SetupShapesPrimitive } from './SetupShapesPrimitive';
import { EMPTY_SCENE, type Scene, type SceneWord } from './sceneTypes';
import { lineWords, runMarks, usePriceScaleWidth } from './paneScene';
import { ShapeTip, shapeStory, useShapeHover } from './ShapeTip';
import { useStockReadContext } from './StockReadContext';
import { STOCK_READ_FOCUS_AFTER_SEC, STOCK_READ_FOCUS_BEFORE_SEC } from './constants';
import type { SetupLeg } from './types';
import { draggedPlan, usePlanDrag } from './usePlanDrag';

const MIN = 60;
/** A time further than this from any bar of the pane is not on it. */
const SNAP_SLACK_SEC = 15 * MIN;
const LEG_LOOKBACK_SEC = 20 * MIN;
/** Room right of the last candle for the plan's zones on the 1-minute pane. */
const PLAN_RIGHT_OFFSET_BARS = 12;
/** Candles shown before a setup begins when the pane frames it, and the fewest it shows. */
const FRAME_PAD_BARS = 12;
const FRAME_MIN_BARS = 40;
/** Room kept between the corner chips and the first word under them, and between the legend and the axis. */
const CORNER_GAP_PX = 3;
const STYLE: Record<PriceLineSpec['style'], LineStyle> = { solid: 0, dotted: 1, dashed: 2 };

function seriesIndex(series: ISeriesApi<'Candlestick'> | null): SeriesTimeIndex {
  return buildSeriesTimeIndex(series ? series.data().map(d => d.time) : []);
}

/** Epoch seconds -> this pane's nearest bar time, or null when no bar is near. */
export function snapper(index: SeriesTimeIndex): (epochSec: number) => Time | null {
  return (epochSec: number) => {
    const target = etChartSeconds(epochSec * 1000);
    const t = nearestSeriesTime(index, target);
    if (t === null) return null;
    return Math.abs(toCanonicalTime(t) - target) <= SNAP_SLACK_SEC ? t : null;
  };
}

/** The lowest low in the pane's candles in the 20 minutes up to a leg's high: where the leg began. */
function legStartOf(series: ISeriesApi<'Candlestick'> | null): (leg: SetupLeg) => number {
  return (leg: SetupLeg) => {
    const fallback = leg.t - 5 * MIN;
    if (!series) return fallback;
    const top = etChartSeconds(leg.t * 1000);
    let best: { t: number; low: number } | null = null;
    for (const d of series.data()) {
      const t = toCanonicalTime(d.time);
      if (t < top - LEG_LOOKBACK_SEC || t > top) continue;
      const low = (d as { low?: number }).low;
      if (typeof low === 'number' && (best === null || low <= best.low)) best = { t, low };
    }
    return best ? leg.t - (top - best.t) : fallback;
  };
}

/**
 * Show the pane's candles from a little before `fromSec` to its last one and the plan's room after it.
 * The range is bar positions, so they are read from the candles the pane holds now: an index kept from
 * an earlier render counts other bars once the series has changed under it.
 */
export function frameFrom(
  chart: ChartPaneOverlayProps['chart'],
  series: ISeriesApi<'Candlestick'> | null,
  fromSec: number,
): boolean {
  const index = seriesIndex(series);
  const n = index.canonical.length;
  if (!chart || n === 0) return false;
  const target = etChartSeconds(fromSec * 1000);
  let i = index.canonical.findIndex(t => t >= target);
  if (i < 0) i = n - 1;
  const from = Math.max(0, Math.min(i - FRAME_PAD_BARS, n - 1 - FRAME_MIN_BARS));
  chart.timeScale().setVisibleLogicalRange({ from, to: n - 1 + PLAN_RIGHT_OFFSET_BARS });
  return true;
}

/** Slide a view that follows the live edge so the plan's zones have room past the last candle; a view
 * the operator moved elsewhere stays where it is. */
export function roomAtLiveEdge(chart: NonNullable<ChartPaneOverlayProps['chart']>, barCount: number): void {
  const last = barCount - 1;
  try {
    const ts = chart.timeScale();
    const range = ts.getVisibleLogicalRange();
    if (!range || !isFollowingRightEdge(range, barCount) || range.to >= last + PLAN_RIGHT_OFFSET_BARS) return;
    const shift = last + PLAN_RIGHT_OFFSET_BARS - range.to;
    ts.setVisibleLogicalRange({ from: range.from + shift, to: range.to + shift });
  } catch {
    /* the chart is gone */
  }
}

function usePriceLines(series: ISeriesApi<'Candlestick'> | null, specs: PriceLineSpec[]): void {
  const lines = useRef(new Map<string, IPriceLine>());
  const key = JSON.stringify(specs);
  useEffect(() => {
    if (!series) return;
    const map = lines.current;
    const want = new Map(specs.map(s => [s.id, s]));
    for (const [id, line] of map) {
      if (!want.has(id)) {
        try {
          series.removePriceLine(line);
        } catch {
          /* the series is gone with its chart */
        }
        map.delete(id);
      }
    }
    for (const s of specs) {
      const opts = {
        price: s.price,
        color: s.color,
        lineWidth: s.width,
        lineStyle: STYLE[s.style],
        axisLabelVisible: s.axisLabel,
        title: s.title,
      } as const;
      const have = map.get(s.id);
      if (have) have.applyOptions(opts);
      else map.set(s.id, series.createPriceLine(opts));
    }
  }, [series, key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => {
    for (const line of lines.current.values()) {
      try {
        series?.removePriceLine(line);
      } catch {
        /* the series is gone with its chart */
      }
    }
    lines.current.clear();
  }, [series]);
}

export function StockReadChartLayer({ timeframe, chart, candleSeriesRef, containerRef, barsRevision }: ChartPaneOverlayProps) {
  const ctx = useStockReadContext();
  const series = chart ? candleSeriesRef.current : null;
  const kind = paneKind(timeframe);
  const daily = timeframe === '1Day';
  const enabled = !!ctx && !ctx.replay && kind !== 'none';
  const live = enabled ? ctx?.read.data ?? null : null;
  // The operator's own plan moves under the pointer on the 1-minute pane; the target follows at 2R.
  const setManualPlan = ctx?.setManualPlan;
  const preview = usePlanDrag({
    containerRef,
    series,
    plan: live?.plan?.source === 'manual' ? live.plan : null,
    enabled: enabled && kind === 'full' && ctx?.layers.setups === true,
    onCommit: (entry, stop) => setManualPlan?.(entry, stop),
  });
  const read = useMemo(
    () => (preview && live?.plan ? { ...live, plan: draggedPlan(live.plan, preview) } : live),
    [live, preview],
  );
  const index = useMemo(() => seriesIndex(series), [series, barsRevision]); // eslint-disable-line react-hooks/exhaustive-deps
  const focusEvent = ctx?.focus?.event ?? null;
  // Who trades (ADR 037): the levels with what stands behind them (a drag shows the plan's own), the pin.
  const levels = preview ? null : ctx?.who.levels ?? null;
  const call = ctx?.who.moment?.call ?? null;
  const past = ctx?.past.data?.symbol === ctx?.symbol ? ctx?.past.data?.episodes ?? null : null;
  const past5 = ctx?.past5?.data?.symbol === ctx?.symbol ? ctx?.past5?.data?.episodes ?? null : null;
  const draw = useMemo(() => paneDraw(read, {
    pane: kind,
    layers: ctx?.layers ?? { setups: false, levels: false, past: false, labels: 'compact', hidden: [], plan: 'auto' },
    toTime: snapper(index),
    legStart: legStartOf(series),
    focus: ctx?.focus ? {
      ts: ctx.focus.ts,
      title: focusEvent ? focusEvent.title.slice(0, 48) : '',
      setup: focusEvent?.levels?.setup ?? null,
    } : null,
    levels,
    call,
    past,
    past5,
  }), [read, kind, ctx?.layers, index, series, ctx?.focus, focusEvent, levels, call, past, past5]);
  const hover = useShapeHover(chart, (kind === 'full' || kind === 'map' || kind === 'daily') && enabled, containerRef);
  const story = hover && read ? shapeStory(hover.id, read, past, past5) : null;

  // The right edge is this scene's: the series' tags and the position tag's room come to its column.
  const claims = !!series && enabled;
  useEffect(() => (chart && claims ? claimEdge(chart) : undefined), [chart, claims]);
  const edge = useSyncExternalStore(
    useCallback((onChange: () => void) => subscribeEdge(chart, onChange), [chart]),
    () => edgeContents(chart),
  );
  const scaleWidth = usePriceScaleWidth(chart, containerRef, barsRevision, kind === 'full' && enabled);
  const [cornerBottom, setCornerBottom] = useState(0);
  const runs = daily && enabled ? ctx?.history.data?.runs ?? null : null;
  const scene = useMemo<Scene>(() => {
    if (!enabled) return EMPTY_SCENE;
    const words: SceneWord[] = [
      ...lineWords(draw.lines),
      ...edge.words.map(w => ({ id: w.id, text: w.text, color: w.color, priority: w.priority, price: null,
        series: w.series, valueWhenOff: w.valueWhenOff })),
    ];
    return {
      ...draw.scene,
      words,
      reserves: edge.reserves.map(r => ({ price: r.price, height: r.height })),
      topInset: kind === 'full' && cornerBottom > 0 ? cornerBottom + CORNER_GAP_PX : 0,
      marks: runs ? runMarks(runs, index) : [],
    };
  }, [enabled, draw, edge, kind, cornerBottom, runs, index]);

  // The shapes: one primitive per pane, fed a new scene whenever the read or the bars change.
  const primitive = useRef<SetupShapesPrimitive | null>(null);
  useEffect(() => {
    if (!series || kind === 'none' || !enabled) return;
    const p = new SetupShapesPrimitive();
    series.attachPrimitive(p);
    primitive.current = p;
    return () => {
      try {
        series.detachPrimitive(p);
      } catch {
        /* the series is gone with its chart */
      }
      if (primitive.current === p) primitive.current = null;
    };
  }, [series, kind, enabled]);
  useEffect(() => {
    primitive.current?.setScene(scene);
  }, [scene]);

  // The lines keep their prices on the axis; their names are the column's.
  const lines = useMemo(() => (enabled ? draw.lines.map(l => ({ ...l, title: '' })) : []), [enabled, draw.lines]);
  usePriceLines(series, lines);

  // Room for the plan's zones right of the last candle when they appear, and only for a view that
  // follows the live edge. The time scale's rightOffset used to do this: it is the scroll position, so
  // the pane jumped to the live edge whenever the zones came or went -- a buy, a sale, a tab shown again.
  const zones = kind === 'full' && draw.scene.boxes.some(b => b.t2 === null);
  const roomPending = useRef(true);
  useEffect(() => {
    if (!zones) {
      roomPending.current = true;
      return;
    }
    const n = series ? series.data().length : 0;
    if (!chart || n === 0 || !roomPending.current) return;
    roomPending.current = false;
    roomAtLiveEdge(chart, n);
  }, [chart, series, zones, barsRevision]);

  // "Show on chart" from the decisions: frame the moment on the 1-minute pane.
  const nonce = ctx?.focus?.nonce ?? 0;
  const focusTs = ctx?.focus?.ts ?? null;
  const hadFocus = useRef(false);
  useEffect(() => {
    if (!chart || kind !== 'full' || !enabled) return;
    if (focusTs === null) {
      if (hadFocus.current) chart.timeScale().scrollToRealTime();
      hadFocus.current = false;
      return;
    }
    hadFocus.current = true;
    const from = etChartSeconds((focusTs - STOCK_READ_FOCUS_BEFORE_SEC) * 1000) as Time;
    const to = etChartSeconds((focusTs + STOCK_READ_FOCUS_AFTER_SEC) * 1000) as Time;
    try {
      chart.timeScale().setVisibleRange({ from, to });
    } catch {
      /* the range is outside the loaded bars: the pane keeps its view */
    }
  }, [chart, kind, nonce, focusTs, enabled]);

  // A forming setup sits a few pixels wide at the pane's right edge: frame it once per setup, and
  // again whenever the operator presses the badge. Their own zoom is theirs until a new setup.
  const lead = read ? leadLane(read) : null;
  const startSec = lead && ctx?.layers.setups ? laneStartSec(lead, legStartOf(series)) : null;
  const frameKey = lead && startSec !== null ? `${ctx?.symbol}:${lead.setup_type}:${lead.leg?.t ?? startSec}` : null;
  const frame = useCallback(() => {
    if (startSec === null || kind !== 'full') return;
    hadFocus.current = false; // leaving a decision for the setup: no scroll back to now after it
    ctx?.clearFocus();
    frameFrom(chart, series, startSec);
  }, [chart, series, startSec, kind, ctx]);
  const framed = useRef<string | null>(null);
  useEffect(() => {
    if (kind !== 'full' || !enabled || !frameKey || framed.current === frameKey || focusTs !== null) return;
    if (startSec !== null && frameFrom(chart, series, startSec)) framed.current = frameKey;
  }, [chart, series, index, kind, enabled, frameKey, startSec, focusTs]);

  if (!ctx || !enabled || !read) return null;
  if (kind === 'full') {
    return (
      <>
        <ChartLegend ctx={ctx} read={read} onFrame={frame} right={scaleWidth > 0 ? scaleWidth + CORNER_GAP_PX : null}
          containerRef={containerRef} onCornerBottom={setCornerBottom} />
        {story && hover && <ShapeTip story={story} hover={hover} />}
      </>
    );
  }
  const levelWords = ctx.layers.levels && (kind === 'map' || kind === 'daily') ? levelNote(read, kind) : null;
  const note = [daily && runs && runs.length > 0 ? `Runs of +40% marked (${runs.length})` : null, levelWords]
    .filter(Boolean).join(' · ');
  return (
    <>
      <div className="sr-pane-top">
        {note && (
          <div className="sr-pane-note" data-testid={daily ? 'stock-read-daily-note' : 'stock-read-levels-note'}>
            {note}
          </div>
        )}
        <ChartKey sections={chartKey(kind, ctx.layers)} testId={`stock-read-key-${kind}`} />
      </div>
      {story && hover && <ShapeTip story={story} hover={hover} />}
    </>
  );
}
