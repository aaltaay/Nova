/**
 * The stock read on one chart pane (ADR 036). The 1-minute pane gets the setups' shapes, the plan's
 * zones and lines, the day's levels, a legend of the lanes and the plan's badge; the 5-minute and
 * 10-second panes mirror the plan's levels as thin lines; the daily pane marks every +40% run.
 * Nothing is drawn while the desk replays another moment: the read is today's live stock.
 */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  createSeriesMarkers,
  type IPriceLine,
  type ISeriesApi,
  type LineStyle,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import { buildSeriesTimeIndex, nearestSeriesTime, toCanonicalTime, type ChartPaneOverlayProps, type SeriesTimeIndex } from '../chart';
import { etChartSeconds } from '../tickerChartData';
import { ChartLegend } from './ChartLegend';
import { laneStartSec, leadLane, paneDraw, paneKind, type PriceLineSpec } from './chartShapes';
import { EMPTY_SCENE, SetupShapesPrimitive } from './SetupShapesPrimitive';
import { useStockReadContext } from './StockReadContext';
import { STOCK_READ_FOCUS_AFTER_SEC, STOCK_READ_FOCUS_BEFORE_SEC } from './constants';
import type { RunDay, SetupLeg } from './types';
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

/** Show the pane's candles from a little before `fromSec` to its last one and the plan's room after it. */
function frameFrom(chart: ChartPaneOverlayProps['chart'], index: SeriesTimeIndex, fromSec: number): boolean {
  const n = index.canonical.length;
  if (!chart || n === 0) return false;
  const target = etChartSeconds(fromSec * 1000);
  let i = index.canonical.findIndex(t => t >= target);
  if (i < 0) i = n - 1;
  const from = Math.max(0, Math.min(i - FRAME_PAD_BARS, n - 1 - FRAME_MIN_BARS));
  chart.timeScale().setVisibleLogicalRange({ from, to: n - 1 + PLAN_RIGHT_OFFSET_BARS });
  return true;
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

function runMarkers(runs: RunDay[], index: SeriesTimeIndex): SeriesMarker<Time>[] {
  const out: SeriesMarker<Time>[] = [];
  for (const r of runs) {
    const target = toCanonicalTime(r.date as Time);
    const t = nearestSeriesTime(index, target);
    if (t === null || Math.abs(toCanonicalTime(t) - target) > 86_400) continue;
    out.push({
      time: t,
      position: 'aboveBar',
      shape: 'arrowDown',
      color: r.today ? '#30d158' : '#f59e0b',
      text: `${r.today ? 'today ' : ''}+${Math.round(r.run_pct * 100)}%`,
    });
  }
  return out;
}

export function StockReadChartLayer({ timeframe, chart, candleSeriesRef, containerRef, barsRevision }: ChartPaneOverlayProps) {
  const ctx = useStockReadContext();
  const series = chart ? candleSeriesRef.current : null;
  const kind = paneKind(timeframe);
  const daily = timeframe === '1Day';
  const enabled = !!ctx && !ctx.replay && (kind !== 'none' || daily);
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
  const draw = useMemo(() => paneDraw(read, {
    pane: kind,
    layers: ctx?.layers ?? { setups: false, levels: false, hidden: [], plan: 'auto' },
    toTime: snapper(index),
    legStart: legStartOf(series),
    focus: ctx?.focus ? {
      ts: ctx.focus.ts,
      title: focusEvent ? focusEvent.title.slice(0, 48) : '',
      setup: focusEvent?.levels?.setup ?? null,
    } : null,
  }), [read, kind, ctx?.layers, index, series, ctx?.focus, focusEvent]);

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
    primitive.current?.setScene(enabled ? draw.scene : EMPTY_SCENE);
  }, [draw, enabled]);

  usePriceLines(series, enabled ? draw.lines : []);

  // Room for the plan's zones right of the last candle, only while they are drawn.
  const zones = kind === 'full' && draw.scene.boxes.some(b => b.t2 === null);
  useEffect(() => {
    if (!chart || !zones) return;
    chart.timeScale().applyOptions({ rightOffset: PLAN_RIGHT_OFFSET_BARS });
    return () => {
      try {
        chart.timeScale().applyOptions({ rightOffset: 0 });
      } catch {
        /* the chart is gone */
      }
    };
  }, [chart, zones]);

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
    frameFrom(chart, index, startSec);
  }, [chart, index, startSec, kind, ctx]);
  const framed = useRef<string | null>(null);
  useEffect(() => {
    if (kind !== 'full' || !enabled || !frameKey || framed.current === frameKey || focusTs !== null) return;
    if (startSec !== null && frameFrom(chart, index, startSec)) framed.current = frameKey;
  }, [chart, index, kind, enabled, frameKey, startSec, focusTs]);

  // The daily pane: every +40% run over the prior close, marked on its bar.
  const runs = daily && enabled ? ctx?.history.data?.runs ?? null : null;
  useEffect(() => {
    if (!series || !runs || runs.length === 0) return;
    const plugin = createSeriesMarkers(series, runMarkers(runs, index));
    return () => {
      try {
        plugin.setMarkers([]);
        plugin.detach();
      } catch {
        /* the series is gone with its chart */
      }
    };
  }, [series, runs, index]);

  if (!ctx || !enabled || !read) return null;
  if (kind === 'full') return <ChartLegend ctx={ctx} read={read} onFrame={frame} />;
  if (daily && runs && runs.length > 0) {
    return (
      <div className="sr-pane-note" data-testid="stock-read-daily-note">
        Runs of +40% marked ({runs.length})
      </div>
    );
  }
  return null;
}
