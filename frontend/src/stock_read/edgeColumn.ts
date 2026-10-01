/**
 * The words at a pane's right edge, laid out as one column (operator report 2026-09-30: "everything is
 * getting on top of each other in the charts!"). A level's name, the EMAs' and VWAP's tags, the plan's
 * ENTRY / STOP / TARGET and the tags for prices out of view had three owners -- the levels stacked among
 * themselves, lightweight-charts drew the series' and price lines' titles on its own, the tags sat at a fixed
 * spot -- so they landed on each other. Here they are placed together:
 * - a word sits on its line when there is room, else a crowd is centred on its lines, never two crossing, so
 *   the column reads in the lines' order, and a hairline runs from a moved word back to its line;
 * - a crowd that cannot sit within `COLUMN_MAX_SHIFT_PX` of its lines drops its least important word first,
 *   and a level that loses its label keeps an axis tick that opens its card;
 * - room something else holds (the position tag) is never covered;
 * - the tags for prices out of view stack at the top, under the pane's corner chips, and at the bottom.
 * Pure: the text measure is an argument, so it runs without a canvas.
 */
import { alpha, fitText, type LevelHit } from './levelRender';
import { drawLabel, inkFor, LABEL_FONT, LABEL_H, type LabelRect } from './sceneLabels';

export const COLUMN_STEP = LABEL_H + 1;
/** A word never sits further than this from its line; past it the least important word in its crowd goes. */
export const COLUMN_MAX_SHIFT_PX = 3 * COLUMN_STEP;
/** At most this many tags for prices out of view at each end. */
export const COLUMN_MAX_TAGS = 3;
/** Room kept free from the pane's top and bottom edges. */
const COLUMN_EDGE_PX = 1;
/** The column ends this far from the pane's right edge: the axis ticks and the hairlines live there. */
const COLUMN_RIGHT_PX = 13;
const TICK_PX = 9;
const TICK_HIT_PX = 4;
/** A word takes at most this share of the pane's width; a longer one drops its last reasons. */
const COLUMN_MAX_SHARE = 0.6;
/** A word this close to its line needs no hairline. */
const LEADER_MIN_PX = 2;

export interface ColumnItem {
  /** Its line's y on the pane (may be off it). */
  y: number;
  text: string;
  color: string;
  /** `filled`: the line's colour behind the words (a series' or a price line's own tag); `plain`: coloured
   * words on dark (a level's name, a tag). */
  style: 'filled' | 'plain';
  /** Higher keeps its place in a crowd. */
  priority: number;
  hoverId: string | null;
  /** Out of view: its tag at the top or bottom ("↑ HOD 9.79"); null leaves it out. */
  offText: string | null;
}

/** Room the column leaves alone, as a band of the pane's height. */
export interface ColumnReserve {
  top: number;
  bottom: number;
}

export interface ColumnSlot {
  item: number;
  text: string;
  /** The label's middle. */
  y: number;
  /** The line it names, for the hairline; null for a tag. */
  lineY: number | null;
}

export interface ColumnLayout {
  slots: ColumnSlot[];
  /** Words in view that found no room. */
  dropped: number[];
}

interface Band {
  top: number;
  bottom: number;
  members: number[];
}

/** The top of a run of `n` words centred on `mean`, kept inside [lo, hi] (the run's first and last middles). */
function runTop(mean: number, n: number, lo: number, hi: number): number {
  const t = mean - ((n - 1) * COLUMN_STEP) / 2;
  return Math.min(Math.max(t, lo), hi - (n - 1) * COLUMN_STEP);
}

/**
 * Where each of `ys` (sorted) goes inside [lo, hi]: runs that would touch merge and are centred on their
 * lines' mean, until none touches. Returns each word's middle and the run it ended in. The caller has made
 * sure they fit.
 */
export function centreRuns(ys: number[], lo: number, hi: number): { at: number[]; run: number[] } {
  const runs = ys.map((y, i) => ({ first: i, n: 1, sum: y }));
  let merged = true;
  while (merged) {
    merged = false;
    for (let k = 0; k + 1 < runs.length; k += 1) {
      const a = runs[k];
      const b = runs[k + 1];
      const aTop = runTop(a.sum / a.n, a.n, lo, hi);
      const bTop = runTop(b.sum / b.n, b.n, lo, hi);
      if (aTop + a.n * COLUMN_STEP > bTop + 1e-6) {
        a.n += b.n;
        a.sum += b.sum;
        runs.splice(k + 1, 1);
        merged = true;
        break;
      }
    }
  }
  const at: number[] = [];
  const run: number[] = [];
  runs.forEach((r, k) => {
    const top = runTop(r.sum / r.n, r.n, lo, hi);
    for (let j = 0; j < r.n; j += 1) {
      at.push(top + j * COLUMN_STEP);
      run.push(k);
    }
  });
  return { at, run };
}

/** The least important of `members` (ties: the one placed furthest from its line, then the last). */
function weakest(items: ColumnItem[], members: number[], shift: (i: number) => number): number {
  let out = members[0];
  for (const i of members.slice(1)) {
    const a = items[i];
    const b = items[out];
    if (a.priority < b.priority || (a.priority === b.priority && shift(i) >= shift(out))) out = i;
  }
  return out;
}

/** One band's words placed: as many as fit, each within reach of its line. */
function placeBand(items: ColumnItem[], band: Band, dropped: number[]): ColumnSlot[] {
  const lo = band.top + LABEL_H / 2;
  const hi = band.bottom - LABEL_H / 2;
  let alive = [...band.members].sort((a, b) => items[a].y - items[b].y);
  const capacity = hi < lo ? 0 : Math.floor((hi - lo) / COLUMN_STEP) + 1;
  while (alive.length > capacity) {
    const w = weakest(items, alive, () => 0);
    dropped.push(w);
    alive = alive.filter(i => i !== w);
  }
  for (;;) {
    if (alive.length === 0) return [];
    const { at, run } = centreRuns(alive.map(i => items[i].y), lo, hi);
    const shift = (i: number) => Math.abs(at[alive.indexOf(i)] - items[i].y);
    let worst = -1;
    alive.forEach((i, k) => {
      if (shift(i) > COLUMN_MAX_SHIFT_PX && (worst < 0 || shift(i) > shift(alive[worst]))) worst = k;
    });
    if (worst < 0) {
      return alive.map((i, k) => ({ item: i, text: items[i].text, y: at[k], lineY: items[i].y }));
    }
    const crowd = alive.filter((_, k) => run[k] === run[worst]);
    const w = weakest(items, crowd, shift);
    dropped.push(w);
    alive = alive.filter(i => i !== w);
  }
}

/** Where every word goes on a pane `height` tall whose corner chips cover the top `topInset` pixels. */
export function layoutColumn(items: ColumnItem[], height: number, topInset = 0,
  reserves: ColumnReserve[] = []): ColumnLayout {
  const ups: number[] = [];
  const downs: number[] = [];
  const inView: number[] = [];
  items.forEach((it, i) => {
    if (it.y >= 0 && it.y <= height) inView.push(i);
    else if (it.offText) (it.y < 0 ? ups : downs).push(i);
  });
  const keep = (list: number[]) => [...list]
    .sort((a, b) => items[b].priority - items[a].priority || Math.abs(items[a].y) - Math.abs(items[b].y))
    .slice(0, COLUMN_MAX_TAGS);
  // Highest price at the top of each stack, lowest at the bottom: the stacks read in price order.
  const top = keep(ups).sort((a, b) => items[a].y - items[b].y);
  const bottom = keep(downs).sort((a, b) => items[a].y - items[b].y);
  const slots: ColumnSlot[] = [];
  const first = topInset + COLUMN_EDGE_PX + LABEL_H / 2;
  top.forEach((i, k) => slots.push({ item: i, text: `↑ ${items[i].offText}`, y: first + k * COLUMN_STEP, lineY: null }));
  const last = height - COLUMN_EDGE_PX - LABEL_H / 2;
  bottom.forEach((i, k) => slots.push({ item: i, text: `↓ ${items[i].offText}`,
    y: last - (bottom.length - 1 - k) * COLUMN_STEP, lineY: null }));

  // The free bands between the tag stacks and around the room others hold; each word joins the band its
  // line is in (a line inside held room joins the nearer side).
  const lo = topInset + COLUMN_EDGE_PX + top.length * COLUMN_STEP;
  const hi = height - COLUMN_EDGE_PX - bottom.length * COLUMN_STEP;
  const held = reserves.filter(r => r.bottom > lo && r.top < hi).sort((a, b) => a.top - b.top);
  const bands: Band[] = [];
  let from = lo;
  for (const r of held) {
    bands.push({ top: from, bottom: Math.max(from, r.top), members: [] });
    from = Math.max(from, r.bottom);
  }
  bands.push({ top: from, bottom: Math.max(from, hi), members: [] });
  const dropped: number[] = [];
  for (const i of inView) {
    const y = items[i].y;
    let best = bands[0];
    let gap = Infinity;
    for (const b of bands) {
      const d = y < b.top ? b.top - y : y > b.bottom ? y - b.bottom : 0;
      if (d < gap) {
        gap = d;
        best = b;
      }
    }
    best.members.push(i);
  }
  for (const b of bands) slots.push(...placeBand(items, b, dropped));
  return { slots, dropped };
}

/** A word on the line's own colour, with ink that reads on it. */
function drawFilled(ctx: CanvasRenderingContext2D, text: string, left: number, y: number, width: number,
  color: string): void {
  ctx.fillStyle = color;
  ctx.fillRect(left, y - LABEL_H / 2, width, LABEL_H);
  ctx.font = LABEL_FONT;
  ctx.fillStyle = inkFor(color);
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'left';
  ctx.fillText(text, left + 4, y + 0.5);
}

/** The column drawn: hairlines, words, and an axis tick for a level that lost its label. Returns the words'
 * and ticks' hover targets, and the rectangles they hold (for the other labels to keep clear of). */
export function drawColumn(
  ctx: CanvasRenderingContext2D,
  items: ColumnItem[],
  layout: ColumnLayout,
  width: number,
  measure: (text: string) => number,
): { hits: LevelHit[]; rects: LabelRect[] } {
  const hits: LevelHit[] = [];
  const rects: LabelRect[] = [];
  ctx.lineWidth = 1;
  ctx.setLineDash([]);
  for (const s of layout.slots) {
    const it = items[s.item];
    const text = fitText(s.text, width * COLUMN_MAX_SHARE, measure);
    const w = measure(text);
    const left = width - COLUMN_RIGHT_PX - w;
    if (s.lineY !== null && Math.abs(s.y - s.lineY) >= LEADER_MIN_PX) {
      ctx.strokeStyle = alpha(it.color, 0.8);
      ctx.beginPath();
      ctx.moveTo(left + w, s.y);
      ctx.lineTo(width - 1, s.lineY);
      ctx.stroke();
    }
    if (it.style === 'filled' && s.lineY !== null) drawFilled(ctx, text, left, s.y, w, it.color);
    else drawLabel(ctx, text, left, s.y, w, it.color);
    const rect = { left, right: left + w, top: s.y - LABEL_H / 2, bottom: s.y + LABEL_H / 2 };
    rects.push(rect);
    if (it.hoverId) hits.push({ rect, hoverId: it.hoverId });
  }
  ctx.lineWidth = 2;
  for (const i of layout.dropped) {
    const it = items[i];
    if (!it.hoverId) continue;
    ctx.strokeStyle = it.color;
    ctx.beginPath();
    ctx.moveTo(width - TICK_PX, Math.round(it.y) + 0.5);
    ctx.lineTo(width, Math.round(it.y) + 0.5);
    ctx.stroke();
    const rect = { left: width - TICK_PX - TICK_HIT_PX, right: width, top: it.y - TICK_HIT_PX, bottom: it.y + TICK_HIT_PX };
    rects.push(rect);
    hits.push({ rect, hoverId: it.hoverId });
  }
  ctx.lineWidth = 1;
  return { hits, rects };
}
