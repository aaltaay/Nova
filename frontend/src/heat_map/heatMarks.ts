/**
 * The heat map's marks over the book (ADR 061 amendment 2026-10-21; operator-approved mockup v4). Where a bright line
 * shrank or ended, the book watcher's verdict: a cap on the line and a chip -- slate "✓ 3,719" traded, amber "✕ 2,000"
 * pulled (solid when it was pulled as the price came closer), the Level 2 ladder's own words and colours. A hidden buyer
 * or seller is a violet dashed box along its price for as long as it held, "◆ 97.1K hidden" at its end. The big buy and
 * sell dots carry their shares inside them; grey (between) dots never do -- they mix midpoint, dark and odd-lot prints,
 * and on a busy stock one grey burst can run for seconds.
 *
 * `heatMarkLayout` is pure (the store and the frame's geometry in, positions and words out); `paintHeatMarks` draws it.
 */
import { fmtVolume } from '../utils/quoteFormat';
import {
  HEAT_DOT_LABEL_FONT,
  HEAT_DOT_LABEL_MIN_R,
  HEAT_FLOOR_SHARES,
  HEAT_MARK_CHIP_BG,
  HEAT_MARK_FONT,
  HEAT_MARK_FULL_BELOW,
  HEAT_MARK_HIDDEN,
  HEAT_MARK_HIDDEN_FILL,
  HEAT_MARK_MERGE_PX,
  HEAT_MARK_PULLED,
  HEAT_MARK_TRADED,
  HEAT_MARK_WALL_LEVEL,
} from './heatMapConstants';
import { heatDotRadius, type HeatDot, type HeatWindow } from './heatFrame';
import type { HeatSymbol } from './heatStore';

/** Where the frame puts things: time to x, tick to y, the plot's box and its tick rows. */
export interface HeatMarkGeometry {
  X: (t: number) => number;
  Y: (tick: number) => number;
  plot: { x: number; y: number; w: number; h: number };
  lo: number;
  hi: number;
}

export interface HeatChip {
  x: number;
  /** The chip's middle, vertically. */
  y: number;
  w: number;
  text: string;
  color: string;
  /** Solid amber with dark digits: pulled as the price came closer. */
  solid: boolean;
}

export interface HeatCap {
  x: number;
  y: number;
  h: number;
  color: string;
}

export interface HeatHiddenBox {
  x0: number;
  x1: number;
  y: number;
  h: number;
}

export interface HeatDotNumber {
  x: number;
  y: number;
  text: string;
}

export interface HeatMarkLayout {
  boxes: HeatHiddenBox[];
  caps: HeatCap[];
  chips: HeatChip[];
  numbers: HeatDotNumber[];
}

const CHIP_PAD = 4;
const CHIP_H = 15;
const CHIP_GAP = 4;

/** The shares that read as a wall (the ramp's yellow) at a brightness: fewer as the brightness goes up. */
export function heatWallMin(capLog: number): number {
  const lo = Math.log10(HEAT_FLOOR_SHARES);
  return 10 ** (lo + HEAT_MARK_WALL_LEVEL * (capLog - lo));
}

/** The ladder's way: whole shares below 10,000, then 15.2K. */
export function heatMarkShares(n: number): string {
  const r = Math.round(n);
  return r < HEAT_MARK_FULL_BELOW ? r.toLocaleString('en-US') : fmtVolume(r);
}

/** Inside a dot: 850, 3.7K, 52K. */
export function heatDotShares(n: number): string {
  if (n < 1000) return String(Math.round(n));
  return n < 10_000 ? `${(n / 1000).toFixed(1)}K` : `${Math.round(n / 1000)}K`;
}

interface Run {
  lane: string;
  side: 'bid' | 'ask';
  tick: number;
  traded: boolean;
  x: number;
  xLast: number;
  count: number;
  sum: number;
  max: number;
  approach: boolean;
}

/** Keep a chip inside the plot: past the right edge it goes to the left of its anchor. */
function placeX(want: number, anchor: number, w: number, plot: HeatMarkGeometry['plot']): number {
  if (want + w <= plot.x + plot.w - 2) return want;
  return Math.max(plot.x + 2, anchor - CHIP_GAP - w);
}

/** Every mark for one frame. `measure` gives a chip text's width at HEAT_MARK_FONT. */
export function heatMarkLayout(
  s: HeatSymbol, w: HeatWindow, g: HeatMarkGeometry, opt: { capLog: number; dots: readonly HeatDot[]; top: number },
  measure: (text: string) => number,
): HeatMarkLayout {
  const out: HeatMarkLayout = { boxes: [], caps: [], chips: [], numbers: [] };
  const rowH = g.plot.h / (g.hi - g.lo + 1);
  const inRange = (tick: number) => tick >= g.lo && tick <= g.hi;

  // Hidden buyers and sellers: the price boxed for as long as it held, its hidden size at the end.
  for (const h of s.hidden.values()) {
    const a = Math.max(h.t0, w.t0);
    const b = Math.min(h.t1, w.t1);
    const tick = Math.round(h.price / s.tick);
    if (b < a || !inRange(tick)) continue;
    const y = g.Y(tick);
    const x0 = g.X(a);
    const x1 = Math.max(g.X(b), x0 + 2);
    out.boxes.push({ x0, x1, y, h: rowH });
    const text = `◆ ${heatMarkShares(h.hidden)} hidden`;
    const cw = measure(text) + 2 * CHIP_PAD;
    out.chips.push({ x: placeX(x1 + CHIP_GAP + 2, x1, cw, g.plot), y, w: cw, text, color: HEAT_MARK_HIDDEN, solid: false });
  }

  // How each wall left: a cap where its line was cut, one chip per run (one price, one verdict, chips that would touch).
  const wallMin = heatWallMin(opt.capLog);
  const runs: Run[] = [];
  for (const d of s.drops) {
    if (d.t < w.t0 || d.t > w.t1) continue;
    if ((d.levelBefore ?? d.pulled + d.filled) < wallMin) continue;
    const tick = Math.round(d.price / s.tick);
    if (!inRange(tick)) continue;
    const x = g.X(d.t);
    const color = d.traded ? HEAT_MARK_TRADED : HEAT_MARK_PULLED;
    const capH = Math.max(8, rowH * 0.84);
    out.caps.push({ x, y: g.Y(tick), h: capH, color });
    const lane = `${d.side}|${tick}|${d.traded}`;
    const n = d.traded ? d.filled : d.pulled;
    let run: Run | undefined;
    for (let k = runs.length - 1; k >= 0; k -= 1) {
      if (runs[k].lane === lane) {
        run = runs[k];
        break;
      }
    }
    if (run && x - run.xLast < HEAT_MARK_MERGE_PX) {
      run.count += 1;
      run.sum += n;
      run.max = Math.max(run.max, n);
      run.xLast = x;
      run.approach ||= d.onApproach;
    } else {
      runs.push({ lane, side: d.side, tick, traded: d.traded, x, xLast: x, count: 1, sum: n, max: n, approach: d.onApproach });
    }
  }
  // Traded shares trade once, so a run adds up; an order pulled and put back counts each time, so a pulled run shows
  // its biggest pull and how many times. Chips at one price never overlap: a later one moves right.
  const laneEnd = new Map<string, number>();
  for (const r of runs) {
    const text = r.traded ? `✓ ${heatMarkShares(r.sum)}` : `✕ ${heatMarkShares(r.max)}${r.count > 1 ? ` ×${r.count}` : ''}`;
    const cw = measure(text) + 2 * CHIP_PAD;
    const side = `${r.side}|${r.tick}`;
    const want = Math.max(r.x + CHIP_GAP + 1, (laneEnd.get(side) ?? Number.NEGATIVE_INFINITY) + CHIP_GAP);
    const x = placeX(want, r.x, cw, g.plot);
    laneEnd.set(side, x + cw);
    const dy = (r.side === 'bid' ? 1 : -1) * Math.max(11, rowH * 0.5 + 7);   // bids below their line, asks above
    out.chips.push({ x, y: g.Y(r.tick) + dy, w: cw, text, color: r.traded ? HEAT_MARK_TRADED : HEAT_MARK_PULLED,
      solid: !r.traded && r.approach });
  }

  // The big buy and sell dots carry their shares.
  for (const d of opt.dots) {
    if (d.side === 2 || heatDotRadius(d.shares, opt.top) < HEAT_DOT_LABEL_MIN_R) continue;
    out.numbers.push({ x: g.X(d.t), y: g.Y(d.price / s.tick), text: heatDotShares(d.shares) });
  }
  return out;
}

/** Draw the marks (the plot is clipped by the caller). */
export function paintHeatMarks(ctx: CanvasRenderingContext2D, m: HeatMarkLayout): void {
  ctx.save();
  for (const b of m.boxes) {
    ctx.fillStyle = HEAT_MARK_HIDDEN_FILL;
    ctx.fillRect(b.x0, b.y - b.h / 2, b.x1 - b.x0, b.h);
    ctx.strokeStyle = HEAT_MARK_HIDDEN;
    ctx.lineWidth = 1.6;
    ctx.setLineDash([5, 3]);
    ctx.strokeRect(b.x0, b.y - b.h / 2, b.x1 - b.x0, b.h);
  }
  ctx.setLineDash([]);
  for (const c of m.caps) {
    ctx.fillStyle = c.color;
    ctx.fillRect(c.x - 1.5, c.y - c.h / 2, 3, c.h);
  }
  ctx.font = HEAT_MARK_FONT;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  for (const c of m.chips) {
    ctx.fillStyle = c.solid ? c.color : HEAT_MARK_CHIP_BG;
    ctx.fillRect(c.x, c.y - CHIP_H / 2, c.w, CHIP_H);
    ctx.strokeStyle = c.color;
    ctx.lineWidth = 1;
    ctx.strokeRect(c.x + 0.5, c.y - CHIP_H / 2 + 0.5, c.w - 1, CHIP_H - 1);
    ctx.fillStyle = c.solid ? '#111111' : c.color;
    ctx.fillText(c.text, c.x + CHIP_PAD, c.y + 0.5);
  }
  ctx.font = HEAT_DOT_LABEL_FONT;
  ctx.textAlign = 'center';
  ctx.lineWidth = 2.6;
  ctx.lineJoin = 'round';
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.65)';
  ctx.fillStyle = '#ffffff';
  for (const n of m.numbers) {
    ctx.strokeText(n.text, n.x, n.y + 0.5);
    ctx.fillText(n.text, n.x, n.y + 0.5);
  }
  ctx.restore();
}
