/**
 * ADR 015 — make one stored drawing anchor renderable on every timeframe pane.
 *
 * Panes do not agree on what a `Time` is. Intraday series carry ET-shifted epoch
 * seconds (`tickerChartData.isoToEtTime`); 1Day/1Week/1Month series carry
 * `'YYYY-MM-DD'` business-day strings. Every drawing except the horizontal line
 * resolves its anchor through `timeScale.timeToCoordinate`, which returns null
 * for a time that is not on that pane's scale — so a 1Min anchor of `1756…`
 * silently paints nothing on a 1Day chart.
 *
 * So: persist one canonical epoch second, and snap it to the target pane's
 * nearest real bar time on load. Out-of-window anchors land on the first/last
 * bar, because a level pinned at the chart edge beats a level that vanished.
 */
import type { Time } from 'lightweight-charts';
import type { Anchor, SerializedDrawing } from 'lightweight-charts-drawing';
import { CHART_DRAWING_PRICE_ONLY_TYPES } from '../constants';

/** Series times paired with their canonical epoch, both ascending. */
export interface SeriesTimeIndex {
  times: Time[];
  canonical: number[];
}

/**
 * Epoch seconds for any lightweight-charts `Time`. Business days become UTC
 * midnight, which lines up with the intraday convention of reading ET wall
 * clock through UTC getters — so the two are directly comparable.
 */
export function toCanonicalTime(time: Time | null | undefined): number {
  if (typeof time === 'number') return Number.isFinite(time) ? time : NaN;
  if (typeof time === 'string') {
    const parsed = Date.parse(`${time.slice(0, 10)}T00:00:00Z`);
    return Number.isNaN(parsed) ? NaN : Math.floor(parsed / 1000);
  }
  if (time && typeof time === 'object' && 'year' in time) {
    const { year, month, day } = time as { year: number; month: number; day: number };
    return Math.floor(Date.UTC(year, month - 1, day) / 1000);
  }
  return NaN;
}

export function buildSeriesTimeIndex(times: readonly Time[]): SeriesTimeIndex {
  const keptTimes: Time[] = [];
  const canonical: number[] = [];
  for (const time of times) {
    const epoch = toCanonicalTime(time);
    if (!Number.isFinite(epoch)) continue;
    keptTimes.push(time);
    canonical.push(epoch);
  }
  return { times: keptTimes, canonical };
}

/** Index of the entry in the ascending `canonical` array closest to `target`. */
function nearestIndex(canonical: readonly number[], target: number): number {
  let low = 0;
  let high = canonical.length - 1;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (canonical[mid] < target) low = mid + 1;
    else high = mid;
  }
  // `low` is the first entry >= target; its predecessor may be closer.
  const prev = low - 1;
  if (prev < 0) return low;
  return target - canonical[prev] <= canonical[low] - target ? prev : low;
}

/** The pane bar time closest to a canonical epoch, clamped to the series edges. */
export function nearestSeriesTime(index: SeriesTimeIndex, canonicalTime: number): Time | null {
  if (index.times.length === 0 || !Number.isFinite(canonicalTime)) return null;
  return index.times[nearestIndex(index.canonical, canonicalTime)];
}

/** A horizontal line renders from price alone, so its anchor time is cosmetic. */
export function isPriceOnlyDrawing(type: string): boolean {
  return CHART_DRAWING_PRICE_ONLY_TYPES.includes(type);
}

/**
 * Rewrite every anchor time onto this pane's bar grid. A pane with no bars yet
 * is returned untouched — a horizontal line still paints, and the rest get
 * snapped on the next hydrate once bars land.
 */
export function snapDrawingToSeries(
  drawing: SerializedDrawing,
  index: SeriesTimeIndex,
): SerializedDrawing {
  if (index.times.length === 0) return drawing;
  const anchors: Anchor[] = drawing.anchors.map((anchor) => {
    const snapped = nearestSeriesTime(index, toCanonicalTime(anchor.time));
    return snapped === null ? anchor : { ...anchor, time: snapped };
  });
  return { ...drawing, anchors };
}

/**
 * Collapse a drawing's anchor times back to canonical epochs for storage, so a
 * daily pane persists `1756…` rather than `'2026-08-26'`.
 */
export function toStorableDrawing(drawing: SerializedDrawing): SerializedDrawing | null {
  const anchors: Anchor[] = [];
  for (const anchor of drawing.anchors) {
    const epoch = toCanonicalTime(anchor.time);
    if (!Number.isFinite(epoch) || !Number.isFinite(anchor.price)) return null;
    anchors.push({ ...anchor, time: epoch as Time });
  }
  if (anchors.length === 0) return null;
  return { ...drawing, anchors };
}
