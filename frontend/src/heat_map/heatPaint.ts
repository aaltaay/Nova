/**
 * The heat map's pixels (ADR 061): one canvas, redrawn at most every HEAT_FRAME_MS by `HeatMapView`. The book grid
 * goes into an ImageData at device resolution (each tick a thin glowing line), then the middle line, the dots (cached
 * sphere sprites), the price and time axes, the book now column and the volume bars.
 */
import {
  HEAT_AXIS_W,
  HEAT_BG_SEEN,
  HEAT_BG_UNSEEN,
  HEAT_BOOK_NOW,
  HEAT_BOOK_W,
  HEAT_COL_PX,
  HEAT_DIM,
  HEAT_DIM_LEVEL,
  HEAT_DOT_MID_ALPHA,
  HEAT_ET_ZONE,
  HEAT_FLOOR_SHARES,
  HEAT_FONT,
  HEAT_FONT_BOLD,
  HEAT_GAP,
  HEAT_GAP_MIN_PX,
  HEAT_GREEN,
  HEAT_GREY,
  HEAT_LINE_CORE,
  HEAT_LINE_SOFT,
  HEAT_MARK_FONT,
  HEAT_MID_LINE,
  HEAT_MINUTE_LINE,
  HEAT_MUTED,
  HEAT_RAMP,
  HEAT_RED,
  HEAT_SPHERES,
  HEAT_SUBROWS,
  HEAT_TEXT,
  HEAT_TIME_H,
  HEAT_VOLUME,
  HEAT_VOLUME_BARS,
  HEAT_VOLUME_H,
  heatVolumePer,
} from './heatMapConstants';
import { heatBookAt, heatDotRadius, heatDots, heatGrid, heatMid, heatRange, heatVolume, type HeatWindow } from './heatFrame';
import { heatMarkLayout, paintHeatMarks } from './heatMarks';
import type { HeatSymbol } from './heatStore';

export interface HeatBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface HeatLayout {
  plot: HeatBox;
  axisX: number;
  book: HeatBox;
  volume: HeatBox;
  timeY: number;
}

export interface HeatPaintOptions {
  minDot: number;
  /** log10 of the shares that read red. */
  capLog: number;
}

/** Where everything goes in a canvas of CSS size w x h. */
export function heatLayout(w: number, h: number): HeatLayout {
  const plotW = Math.max(40, w - HEAT_GAP - HEAT_AXIS_W - HEAT_BOOK_W);
  const plotH = Math.max(40, h - HEAT_GAP - HEAT_VOLUME_H - HEAT_TIME_H - HEAT_GAP);
  const plot = { x: HEAT_GAP, y: HEAT_GAP, w: plotW, h: plotH };
  return {
    plot,
    axisX: plot.x + plot.w + 8,
    book: { x: plot.x + plot.w + HEAT_AXIS_W, y: plot.y, w: HEAT_BOOK_W - HEAT_GAP, h: plot.h },
    volume: { x: plot.x, y: plot.y + plot.h + HEAT_GAP, w: plot.w, h: HEAT_VOLUME_H },
    timeY: plot.y + plot.h + HEAT_GAP + HEAT_VOLUME_H + 16,
  };
}

function hexRgb(h: string): [number, number, number] {
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}

const RAMP_RGB = HEAT_RAMP.map(([at, hex]) => [at, ...hexRgb(hex)] as const);

/** The ramp's colour at level v (0..1). */
export function heatColor(v: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, v));
  for (let i = 1; i < RAMP_RGB.length; i += 1) {
    const [a, r0, g0, b0] = RAMP_RGB[i - 1];
    const [b, r1, g1, b1] = RAMP_RGB[i];
    if (x <= b) {
      const f = b === a ? 0 : (x - a) / (b - a);
      return [r0 + (r1 - r0) * f, g0 + (g1 - g0) * f, b0 + (b1 - b0) * f];
    }
  }
  const last = RAMP_RGB[RAMP_RGB.length - 1];
  return [last[1], last[2], last[3]];
}

/** Shares -> 0..1 on a log scale from the floor to the cap. */
export function heatLevel(shares: number, capLog: number): number {
  if (!(shares > 0)) return 0;
  const lo = Math.log10(HEAT_FLOOR_SHARES);
  return Math.min(1, Math.max(0, (Math.log10(shares) - lo) / (capLog - lo)));
}

/** The line profile at distance d (in ticks, 0..0.5) from a tick's middle. */
function profile(d: number, gaps: boolean): number {
  if (!gaps || d <= HEAT_LINE_CORE) return 1;
  return Math.exp(-(((d - HEAT_LINE_CORE) / HEAT_LINE_SOFT) ** 2));
}

let lutCache: Float32Array | null = null;

/** 256 levels: the ramp's colour and the line's strength (small orders dim, from HEAT_DIM_LEVEL up full). */
function colorLut(): Float32Array {
  if (lutCache) return lutCache;
  const lut = new Float32Array(256 * 4);
  for (let q = 0; q < 256; q += 1) {
    const v = q / 255;
    const [r, g, b] = heatColor(v);
    lut[q * 4] = r;
    lut[q * 4 + 1] = g;
    lut[q * 4 + 2] = b;
    lut[q * 4 + 3] = 0.25 + 0.75 * Math.min(1, v / HEAT_DIM_LEVEL);
  }
  lutCache = lut;
  return lut;
}

let scratch: HTMLCanvasElement | null = null;

function paintGrid(ctx: CanvasRenderingContext2D, s: HeatSymbol, w: HeatWindow, lo: number, hi: number,
  box: HeatBox, dpr: number, capLog: number): void {
  const cols = Math.max(1, Math.ceil(box.w / HEAT_COL_PX));
  const grid = heatGrid(s, w, { lo, hi }, cols);
  const pxPerTick = (box.h * dpr) / grid.rows;
  const gaps = pxPerTick >= HEAT_GAP_MIN_PX * dpr;
  const sub = gaps ? HEAT_SUBROWS : 1;
  const height = grid.rows * sub;
  if (!scratch) scratch = document.createElement('canvas');
  scratch.width = cols;
  scratch.height = height;
  const sctx = scratch.getContext('2d');
  if (!sctx) return;
  const img = sctx.createImageData(cols, height);
  const px = img.data;
  const prof = Array.from({ length: sub }, (_, j) => profile(Math.abs((j + 0.5) / sub - 0.5), gaps));
  const lut = colorLut();
  const [sr, sg, sb] = HEAT_BG_SEEN;
  const [ur, ug, ub] = HEAT_BG_UNSEEN;
  const lo10 = Math.log10(HEAT_FLOOR_SHARES);
  const scale = 255 / (capLog - lo10);
  for (let r = 0; r < grid.rows; r += 1) {
    const top = (grid.rows - 1 - r) * sub;   // row 0 is the lowest tick
    for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      const seen = grid.seen[i] === 1;
      const shares = grid.size[i];
      const hot = seen && shares > 0;
      const q = hot ? Math.min(255, Math.max(0, Math.round((Math.log10(shares) - lo10) * scale))) : 0;
      for (let j = 0; j < sub; j += 1) {
        const o = ((top + j) * cols + c) * 4;
        if (!hot) {
          px[o] = seen ? sr : ur;
          px[o + 1] = seen ? sg : ug;
          px[o + 2] = seen ? sb : ub;
        } else {
          const k = lut[q * 4 + 3] * prof[j];
          px[o] = sr + (lut[q * 4] - sr) * k;
          px[o + 1] = sg + (lut[q * 4 + 1] - sg) * k;
          px[o + 2] = sb + (lut[q * 4 + 2] - sb) * k;
        }
        px[o + 3] = 255;
      }
    }
  }
  sctx.putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(scratch, box.x, box.y, box.w, box.h);
  ctx.imageSmoothingEnabled = true;
}

const sprites = new Map<string, HTMLCanvasElement>();

function sprite(side: number, rCss: number, dpr: number): HTMLCanvasElement | null {
  const r = Math.max(1, Math.round(rCss * dpr));
  const key = `${side}:${r}`;
  const hit = sprites.get(key);
  if (hit) return hit;
  const c = document.createElement('canvas');
  c.width = r * 2 + 2;
  c.height = r * 2 + 2;
  const g = c.getContext('2d');
  if (!g) return null;
  const [hiC, mid, rim] = HEAT_SPHERES[side];
  const grad = g.createRadialGradient(r * 0.72 + 1, r * 0.6 + 1, r * 0.1, r + 1, r + 1, r);
  grad.addColorStop(0, hiC);
  grad.addColorStop(0.45, mid);
  grad.addColorStop(1, rim);
  g.fillStyle = grad;
  g.beginPath();
  g.arc(r + 1, r + 1, r, 0, Math.PI * 2);
  g.fill();
  g.strokeStyle = 'rgba(0,0,0,0.35)';
  g.lineWidth = Math.max(1, dpr * 0.7);
  g.stroke();
  sprites.set(key, c);
  return c;
}

const etFmt = new Map<boolean, Intl.DateTimeFormat>();

function etClock(t: number, seconds: boolean): string {
  let f = etFmt.get(seconds);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: HEAT_ET_ZONE, hour: '2-digit', minute: '2-digit', second: seconds ? '2-digit' : undefined, hour12: false,
    });
    etFmt.set(seconds, f);
  }
  return f.format(new Date(t * 1000));
}

function niceStep(choices: readonly number[], perUnitPx: number, minPx: number): number {
  return choices.find((c) => c * perUnitPx >= minPx) ?? choices[choices.length - 1];
}

/** Draw the whole frame. Returns false when there is no book in the window (the view shows why). */
export function paintHeat(ctx: CanvasRenderingContext2D, s: HeatSymbol, w: HeatWindow, cssW: number, cssH: number,
  dpr: number, opt: HeatPaintOptions): boolean {
  const L = heatLayout(cssW, cssH);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, cssW, cssH);
  const range = heatRange(s, w);
  if (!range) return false;
  const { lo, hi } = range;
  const rows = hi - lo + 1;
  const { plot } = L;
  const X = (t: number) => plot.x + ((t - w.t0) / (w.t1 - w.t0)) * plot.w;
  const Y = (tick: number) => plot.y + ((hi + 0.5 - tick) / rows) * plot.h;
  paintGrid(ctx, s, w, lo, hi, plot, dpr, opt.capLog);

  // Minute (or finer) lines, dotted like thinkorswim's, through the plot and the volume bars.
  const span = w.t1 - w.t0;
  const tStep = niceStep([10, 15, 30, 60, 120, 300, 600], plot.w / span, 120);
  ctx.save();
  ctx.strokeStyle = HEAT_MINUTE_LINE;
  ctx.setLineDash([2, 5]);
  ctx.font = HEAT_FONT;
  ctx.fillStyle = HEAT_MUTED;
  ctx.textAlign = 'center';
  for (let t = Math.ceil(w.t0 / tStep) * tStep; t <= w.t1; t += tStep) {
    const x = X(t);
    ctx.beginPath();
    ctx.moveTo(x, plot.y);
    ctx.lineTo(x, L.volume.y + L.volume.h);
    ctx.stroke();
    if (x > plot.x + 24 && x < plot.x + plot.w - 24) ctx.fillText(etClock(t, tStep < 60), x, L.timeY);
  }
  ctx.restore();

  // The middle of the bid and ask: buys sit just above it (at the ask), sells just below (at the bid).
  ctx.save();
  ctx.beginPath();
  ctx.rect(plot.x, plot.y, plot.w, plot.h);
  ctx.clip();
  const midCols = Math.max(1, Math.round(plot.w));
  const mid = heatMid(s, w, midCols);
  ctx.strokeStyle = HEAT_MID_LINE;
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  let pen = false;
  for (let c = 0; c < midCols; c += 1) {
    if (Number.isNaN(mid[c])) {
      pen = false;
      continue;
    }
    const x = plot.x + c + 1;
    const y = Y(mid[c]);
    if (pen) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
    pen = true;
  }
  ctx.stroke();

  // Dots: bursts of buying or selling, area = shares, the window's biggest at HEAT_DOT_R_MAX.
  const dots = heatDots(s, w, opt.minDot);
  const top = dots.length ? dots[0].shares : 1;
  for (const d of dots) {
    const r = heatDotRadius(d.shares, top);
    const img = sprite(d.side, r, dpr);
    if (!img) continue;
    ctx.globalAlpha = d.side === 2 ? HEAT_DOT_MID_ALPHA : 1;
    ctx.drawImage(img, X(d.t) - r - 1 / dpr, Y(d.price / s.tick) - r - 1 / dpr, 2 * r + 2 / dpr, 2 * r + 2 / dpr);
  }
  ctx.globalAlpha = 1;
  // How each wall left, hidden size and the dots' numbers (the book watcher's verdicts, ADR 061 amendment).
  ctx.font = HEAT_MARK_FONT;
  paintHeatMarks(ctx, heatMarkLayout(s, w, { X, Y, plot, lo, hi }, { capLog: opt.capLog, dots, top },
    (text) => ctx.measureText(text).width));
  ctx.restore();

  paintAxis(ctx, s, L, lo, hi, Y);
  paintBookNow(ctx, s, L, w.t1, lo, hi, Y);
  paintVolume(ctx, s, w, L);
  return true;
}

function priceText(s: HeatSymbol, tick: number): string {
  return (tick * s.tick).toFixed(s.tick < 0.01 ? 3 : 2);
}

function paintAxis(ctx: CanvasRenderingContext2D, s: HeatSymbol, L: HeatLayout, lo: number, hi: number,
  Y: (tick: number) => number): void {
  const pxPerTick = L.plot.h / (hi - lo + 1);
  const step = niceStep([1, 2, 5, 10, 25, 50, 100, 250, 500], pxPerTick, 34);
  ctx.textAlign = 'left';
  for (let k = Math.ceil(lo / step) * step; k <= hi; k += step) {
    const major = k % (step * 2) === 0;
    ctx.font = major ? HEAT_FONT_BOLD : HEAT_FONT;
    ctx.fillStyle = major ? HEAT_TEXT : HEAT_MUTED;
    ctx.fillText(priceText(s, k), L.axisX, Y(k) + 4);
  }
  if (s.lastPrice != null) {
    const y = Y(s.lastPrice / s.tick);
    if (y >= L.plot.y && y <= L.plot.y + L.plot.h) {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(L.axisX - 4, y - 10, HEAT_AXIS_W - 10, 20);
      ctx.fillStyle = '#000';
      ctx.font = HEAT_FONT_BOLD;
      ctx.textAlign = 'center';
      ctx.fillText(s.lastPrice.toFixed(s.tick < 0.01 ? 3 : 2), L.axisX - 4 + (HEAT_AXIS_W - 10) / 2, y + 4);
    }
  }
}

function paintBookNow(ctx: CanvasRenderingContext2D, s: HeatSymbol, L: HeatLayout, t: number, lo: number, hi: number,
  Y: (tick: number) => number): void {
  const b = L.book;
  ctx.font = HEAT_FONT_BOLD;
  ctx.fillStyle = HEAT_MUTED;
  ctx.textAlign = 'left';
  ctx.fillText(HEAT_BOOK_NOW, b.x, b.y + 12);
  const sn = heatBookAt(s, t);
  if (!sn) return;
  const rowH = L.plot.h / (hi - lo + 1);
  const barH = Math.max(2, Math.min(16, rowH - 4));
  let max = 0;
  for (let k = Math.max(lo, sn.lo); k <= Math.min(hi, sn.lo + sn.sizes.length - 1); k += 1) max = Math.max(max, sn.sizes[k - sn.lo]);
  if (max <= 0) return;
  for (let k = Math.max(lo, sn.lo); k <= Math.min(hi, sn.lo + sn.sizes.length - 1); k += 1) {
    const v = sn.sizes[k - sn.lo];
    if (v <= 0) continue;
    const ask = Number.isFinite(sn.ba) && k >= sn.ba;
    const y = Y(k);
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = ask ? HEAT_RED : HEAT_GREEN;
    ctx.fillRect(b.x, y - barH / 2, Math.max(3, (v / max) * b.w), barH);
    ctx.globalAlpha = 1;
    if (barH >= 10) {
      ctx.fillStyle = '#ffffff';
      ctx.font = HEAT_FONT_BOLD;
      ctx.fillText(Math.round(v).toLocaleString('en-US'), b.x + 6, y + 4);
    }
  }
}

function paintVolume(ctx: CanvasRenderingContext2D, s: HeatSymbol, w: HeatWindow, L: HeatLayout): void {
  const v = L.volume;
  ctx.fillStyle = '#05070c';
  ctx.fillRect(v.x, v.y, v.w, v.h);
  const bars = heatVolume(s, w, HEAT_VOLUME_BARS);
  const max = Math.max(1, ...bars.map(([a, b, m]) => a + b + m));
  const bw = v.w / bars.length;
  bars.forEach(([ask, bid, mid], i) => {
    let y = v.y + v.h;
    for (const [shares, color] of [[ask, HEAT_GREEN], [mid, HEAT_GREY], [bid, HEAT_RED]] as const) {
      const hh = (shares / max) * (v.h - 6);
      if (hh < 0.5) continue;
      ctx.fillStyle = color;
      ctx.fillRect(v.x + i * bw + 1, y - hh, Math.max(1, bw - 2), hh);
      y -= hh;
    }
  });
  ctx.font = HEAT_FONT_BOLD;
  ctx.fillStyle = HEAT_MUTED;
  ctx.textAlign = 'left';
  ctx.fillText(HEAT_VOLUME, L.axisX, v.y + 14);
  ctx.font = HEAT_FONT;
  ctx.fillStyle = HEAT_DIM;
  ctx.fillText(heatVolumePer((w.t1 - w.t0) / HEAT_VOLUME_BARS), L.axisX, v.y + 30);
}
