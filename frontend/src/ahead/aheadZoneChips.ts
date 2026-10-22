/**
 * Where the words in Ahead's zone go (ADR 065), for `AheadZoneRenderer`: every chip is placed before any is drawn, so
 * the renderer can draw all their backings, then the story paths and their marks over the backings, then the words on
 * top -- a story path is never hidden under a chip -- and no chip ever sits on a mark: the chip moves, never the mark.
 *
 * In order: the meet's words over its ring; each stub's words over its line (slid left past a mark on it, else under
 * the line); a price's odds chip (a wall's) on its price, slid left past a mark there, else nudged down past what is
 * already placed; "neither", tied to no one price, in the free space between the walls (`freeSpot`), or left to the
 * panel's card; the story paths' end labels last, beside their path's end (or its ✓ / ✕), never on it -- and when
 * one cannot sit there, on the side away from the other story paths' coloured stretches first, with a thin leader
 * back to that end. The chips tied to no price first look for a spot off every story path's coloured stretch and
 * settle for any free one. A wall's "if it breaks"
 * line takes the longest of its words that fits in `SUB_MAX_SHARE` of the zone, and is left to the walls card when it
 * would sit on a story path's coloured stretch.
 */
import {
  AHEAD_DRAW, CHIP_H, chipRect, chipWidth, clearance, crosses, nearestOn, onPane, overlaps, topOver, type Pt, type Rect,
  type Seg,
} from './aheadCanvas';
import type { AheadScene } from './aheadSceneTypes';
import { colouredSegs, endAnchor, endSegs, markRects } from './aheadStoryDraw';
import type { Px } from './AheadZoneRenderer';

const MEET_RING_PX = 6;
/** The meet's chip keeps this clear of its ring and of the lines that run into it. */
const MEET_CHIP_GAP_PX = 5;
const CHIP_GAP_PX = 2;
const CHIP_STEP_PX = 20;
/** A stub's words sit this far over (or under) its line, centre to line; this much further when a mark on the line
 * would touch them wherever they slide (clear of a ✓ / ✕ disc on the line itself). */
const STUB_CHIP_DY_PX = 11;
const STUB_CHIP_FAR_DY_PX = 18;
/** An end label sits at its end when its nearest edge is this close to it (past the reach of a ✓ / ✕ there). */
const END_TOUCH_PX = 6;
/** An end label that cannot sit at its end looks this far (centre to its end) on each side, the side away from the
 * other story paths' coloured stretches first; past that, the nearest free spot anywhere. */
const LEADER_REACH_PX = 5 * CHIP_H;
/** The "neither" chip looks for free space this many pixels at a time, outward from the middle it asks for. */
const FREE_STEP_PX = 2;
/** Chips keep this far inside the zone's edges. */
const CHIP_INSET_PX = 4;
/** A wall's "if it breaks" line is never wider than this share of the zone. */
export const SUB_MAX_SHARE = 0.6;

/** One chip to draw: its rectangle, words and colour. */
export interface ChipDraw {
  rect: Rect;
  text: string;
  fg: string;
  /** An end label placed away from its end: the thin line from its nearest edge to that end (or its ✓ / ✕). */
  leader?: { from: Pt; to: Pt; color: string };
}

/** What the layout reads: the zone's pixels, the pane's size, Nova's lines as drawn, and the meet's point. */
export interface ChipLayoutIn {
  px: Px;
  right: number;
  W: number;
  H: number;
  /** The price area's bottom (the volume band's top). */
  floor: number;
  segs: readonly Seg[];
  /** Where the meet's ring is (or where the lines stop, past the zone). */
  meetAt: { x: number; y: number } | null;
}

/**
 * Where a chip tied to no one price goes: the centre nearest `want` between `top` and `bottom` (the walls' lines, or
 * the price area's edges) whose chip `clear` accepts, its whole height inside that space; null when none is free.
 */
export function freeSpot(want: number, top: number, bottom: number, clear: (cy: number) => boolean): number | null {
  const lo = top + CHIP_H / 2;
  const hi = bottom - CHIP_H / 2;
  if (hi < lo) return null;
  const start = Math.min(hi, Math.max(lo, want));
  for (let d = 0; start - d >= lo || start + d <= hi; d += FREE_STEP_PX) {
    for (const cy of d === 0 ? [start] : [start - d, start + d]) {
      if (cy >= lo && cy <= hi && clear(cy)) return cy;
    }
  }
  return null;
}

/** How far the point is from the rectangle (0 inside it). */
function dist(r: Rect, p: Pt): number {
  const q = nearestOn(r, p);
  return Math.hypot(p.x - q.x, p.y - q.y);
}

/** Every chip of the zone, placed; nothing is drawn. */
export function layoutChips(ctx: CanvasRenderingContext2D, inp: ChipLayoutIn): ChipDraw[] {
  const { px, right, W, H, floor, segs } = inp;
  const s: AheadScene = px.scene;
  const bounds = { width: Math.min(W, right + 1), height: H };
  const lo = px.left + CHIP_INSET_PX;
  const hi = right - CHIP_INSET_PX;
  const marks = markRects(px, floor);
  const coloured = colouredSegs(px);
  const out: ChipDraw[] = [];
  const placed: Rect[] = [];
  const add = (rect: Rect, text: string, fg: string, leader?: ChipDraw['leader']) => {
    placed.push(rect);
    out.push(leader ? { rect, text, fg, leader } : { rect, text, fg });
  };
  // Words that fit the zone: the longest that does, slid inside the zone; none when none fits. A chip is never drawn
  // left of the zone, over real candles.
  const fit = (xEnd: number, texts: readonly (string | undefined)[], max = hi - lo) => {
    for (const t of texts) {
      if (!t) continue;
      const w = chipWidth(ctx, t);
      if (w > max) continue;
      return { end: Math.min(hi, Math.max(lo + w, xEnd)), text: t, w };
    }
    return null;
  };
  const onMark = (r: Rect) => marks.some(m => overlaps(m, r, CHIP_GAP_PX));
  const onAny = (list: readonly Seg[], r: Rect) => list.some(g => crosses(g, r, CHIP_GAP_PX));
  const clear = (r: Rect) => onPane(r, bounds) && !onMark(r) && !placed.some(q => overlaps(q, r, CHIP_GAP_PX))
    && !onAny(segs, r);
  // The chip ending at `end` on row `cy`, slid left past each mark it would sit on; null when it cannot clear them
  // inside the zone.
  const offMarks = (end: number, w: number, cy: number): Rect | null => {
    let e = end;
    for (let i = 0; i <= marks.length; i += 1) {
      const r = chipRect(e, w, cy);
      const hit = marks.filter(m => overlaps(m, r, CHIP_GAP_PX));
      if (hit.length === 0) return r;
      e = Math.min(...hit.map(m => m.left)) - CHIP_GAP_PX;
      if (e - w < lo) return null;
    }
    return null;
  };

  // The meet's words: over its ring and over the lines that run into it, with room to spare; higher still past a mark.
  if (s.meet && inp.meetAt) {
    const { x: xm, y: ym } = inp.meetAt;
    const f = fit(xm + chipWidth(ctx, s.meet.text) / 2, [s.meet.text]);
    if (f) {
      const roof = Math.min(ym - MEET_RING_PX, topOver(segs, f.end - f.w, f.end));
      // A steep line could push it off the pane: it then stops at the pane's top.
      let cy = Math.max(CHIP_H / 2 + 1, roof - MEET_CHIP_GAP_PX - CHIP_H / 2);
      while (cy >= CHIP_H / 2 && onMark(chipRect(f.end, f.w, cy))) cy -= CHIP_STEP_PX;
      const r = chipRect(f.end, f.w, cy);
      if (onPane(r, bounds) && !onMark(r)) add(r, f.text, AHEAD_DRAW.text);
    }
  }
  // Each stub's words over its line, or under it when a mark sits there and sliding left cannot clear it.
  for (const h of s.hLines) {
    const y = px.y(h.p);
    const f = y !== null && h.chip ? fit(hi, [h.chip]) : null;
    if (y === null || !f) continue;
    const rows = [STUB_CHIP_DY_PX, STUB_CHIP_FAR_DY_PX].flatMap(dy => [y - dy, y + dy]);
    const r = rows.map(cy => offMarks(f.end, f.w, cy))
      .find((c): c is Rect => c !== null && onPane(c, bounds));
    if (r) add(r, f.text, h.color);
  }

  const located = s.chips.flatMap(c => {
    const y = px.y(c.p);
    return y === null ? [] : [{ c, y }];
  });
  const yielding = (c: (typeof s.chips)[number]) => c.role === 'neither' || c.role === 'story';
  const priced = located.filter(x => !yielding(x.c)).sort((a, b) => a.y - b.y);
  const wallYs = located.filter(x => x.c.role === 'wall').map(x => x.y);
  const neither = located.filter(x => x.c.role === 'neither');
  const ends = located.filter(x => x.c.role === 'story');
  /** The longest of `texts` that fits the zone's share, flush under `main` or else over it, clear of everything. */
  const subLine = (texts: readonly string[], main: Rect): { r: Rect; t: string } | null => {
    const cy = (main.top + main.bottom) / 2;
    for (const t of texts) {
      const w = chipWidth(ctx, t);
      if (w > Math.min(hi - lo, SUB_MAX_SHARE * (right - px.left))) continue;
      const end = Math.min(hi, Math.max(lo + w, main.right));
      const r = [cy + CHIP_H, cy - CHIP_H].map(sy => chipRect(end, w, sy)).find(q => clear(q) && !onAny(coloured, q));
      if (r) return { r, t };
    }
    return null;
  };
  /** Story path `i`'s end label (`box`: its chip on a row; `left..right`: its columns): at its end when a free spot
   * there keeps it close, else away from the other paths' coloured stretches first, with a leader back to its end. It
   * always keeps off its own path's last steps and prefers to keep off every coloured stretch. */
  const endLabel = (i: number, y: number, box: (cy: number) => Rect, left: number, right: number) => {
    const end = endAnchor(px, i, floor);
    const own = endSegs(px, i);
    const want = end?.at.y ?? y;
    const ok = (v: number) => clear(box(v)) && !onAny(own, box(v));
    const free = (v: number) => ok(v) && !onAny(coloured, box(v));
    const span = (a: number, b: number, test: (v: number) => boolean) => freeSpot(want, Math.max(0, a),
      Math.min(floor, b), test);
    const touch = end ? end.r + END_TOUCH_PX : 0;
    const hugs = (v: number) => end !== null && dist(box(v), end.at) <= touch;
    let spot = span(want - CHIP_H - touch, want + CHIP_H + touch, v => free(v) && hugs(v));
    if (spot === null) {
      const up: [number, number] = [want - LEADER_REACH_PX - CHIP_H / 2, want + CHIP_H / 2];
      const down: [number, number] = [want - CHIP_H / 2, want + LEADER_REACH_PX + CHIP_H / 2];
      const near = clearance(colouredSegs(px, i), left, right, want);
      for (const [a, b] of near.above < near.below ? [down, up] : [up, down]) {
        spot = span(a, b, free) ?? span(a, b, ok);
        if (spot !== null) break;
      }
      spot ??= freeSpot(want, 0, floor, ok);
    }
    if (spot === null) return null;
    const rect = box(spot);
    if (!end || hugs(spot)) return { rect };
    const color = px.scene.story[i]?.color ?? AHEAD_DRAW.text;
    return { rect, leader: { from: nearestOn(rect, end.at), to: end.at, color } };
  };
  for (const { c, y } of [...priced, ...neither, ...ends]) {
    const f = fit(hi, [c.text, c.short, c.tiny]);
    if (!f) continue;
    const box = (cy: number) => chipRect(f.end, f.w, cy);
    let rect: Rect | null = null;
    let leader: ChipDraw['leader'];
    if (c.role === 'story') {
      const at = endLabel(c.story ?? -1, y, box, f.end - f.w, f.end);
      rect = at?.rect ?? null;
      leader = at?.leader;
    } else if (c.role === 'neither') {
      const top = Math.max(0, ...wallYs.filter(w => w < y));
      const bottom = Math.min(floor, ...wallYs.filter(w => w > y));
      const ok = (v: number) => clear(box(v));
      const spot = freeSpot(y, top, bottom, v => ok(v) && !onAny(coloured, box(v))) ?? freeSpot(y, top, bottom, ok);
      rect = spot === null ? null : box(spot);
    } else {
      // A price's chip: on its price, slid left past a mark there, else nudged down past what is already placed.
      let cy = y;
      for (let tries = 0; tries < 8 && rect === null; tries += 1) {
        const r = offMarks(f.end, f.w, cy) ?? box(cy);
        if (clear(r)) rect = r;
        else cy += CHIP_STEP_PX;
      }
      if (rect === null && onPane(box(y), bounds) && !onMark(box(y))) rect = box(y);
    }
    if (!rect) continue;
    // A wall's "if it breaks" line: beside the full words only, flush under the chip or else over it, the longest words
    // that fit the zone's share and the space as placed, never on a story path's coloured stretch. Otherwise the walls
    // card alone carries it. It sits flush on its own chip, so only the others can refuse it.
    const sub = c.sub && f.text === c.text ? subLine(c.sub, rect) : null;
    add(rect, f.text, c.color, leader);
    if (sub) add(sub.r, sub.t, c.color);
  }
  return out;
}
