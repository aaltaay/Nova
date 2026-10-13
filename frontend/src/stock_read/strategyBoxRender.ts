/**
 * Placing and drawing a setup's strategy box on the 1-minute pane (`strategyBox.ts` decides it, operator asks
 * 2026-10-12). The box runs to the pane's right edge, under the edge column, whose words name its prices (T2, T1,
 * entry, stop: `strategyWords`). A forming setup's box stands on the setup's window -- from its start, never before the newest
 * candle -- when that leaves room for its name left of the column's words; else it waits at the right edge saying when
 * it starts. Faint and dashed while the setup is only forming; in full colour with a solid outline once it is near or
 * armed, the word for where it stands beside its name. Target 2 is a dotted dash across the box while it
 * is in view; its name is the column's word, and out of view the column's tag (2026-10-13). Drawn before the column, so
 * the column's words read over it.
 */
import { STRATEGY_BOX as S, STRATEGY_BOX_LIVE as L } from './constants';
import { fitText } from './levelRender';
import type { LabelRect } from './sceneLabels';
import type { SceneStrategy } from './sceneTypes';

export interface StrategyPx {
  /** The right edge of the newest candle. */
  xAfter: number;
  /** The window's start and end on the pane; null without them. */
  xStart: number | null;
  xEnd: number | null;
  /** One candle's width. */
  bar: number;
  yEntry: number;
  yStop: number;
  yTarget: number;
  /** Target 2's y (it may be off the pane); null or absent without one. */
  yTarget2?: number | null;
  s: SceneStrategy;
}

export interface StrategySpan {
  x1: number;
  x2: number;
  /** Not on its window: at the right edge, waiting for it. */
  waiting: boolean;
}

/** A short's name ends in this; a name too long for the box is cut before it, so the box always says it is a short. */
const SHORT_TAIL = ' ▼ SHORT';

/** Where the box goes: from its window's start (never before `after`) to its end or the pane's `right` edge. With less
 * than `minText` of it left of the column's words (`inner`) there, it waits at the right edge, `wait` of it clear. */
export function strategySpan(a: { after: number; start: number | null; end: number | null; right: number;
  inner: number; minText: number; wait: number }): StrategySpan {
  const x1 = Math.max(a.after, a.start ?? a.after);
  const x2 = Math.min(a.end ?? a.right, a.right);
  if (Math.min(x2, a.inner) - x1 >= a.minText) return { x1, x2, waiting: false };
  return { x1: Math.max(a.after, a.inner - a.wait), x2: a.right, waiting: true };
}

/** The left of the edge column's words between `top` and `bottom`: the box's words end before it. */
export function columnLeft(width: number, top: number, bottom: number, column: readonly LabelRect[]): number {
  let left = width;
  for (const r of column) {
    if (r.bottom >= top && r.top <= bottom) left = Math.min(left, r.left);
  }
  return left - S.padPx;
}

/** The setup's name in `room`: a short's is cut before its "▼ SHORT" (`fitText` cuts the end). */
export function fitName(name: string, room: number, measure: (t: string) => number): string {
  if (measure(name) <= room || !name.endsWith(SHORT_TAIL)) return fitText(name, room, measure);
  return `${fitText(name.slice(0, -SHORT_TAIL.length), room - measure(SHORT_TAIL), measure)}${SHORT_TAIL}`;
}

/** Draws the box; returns the room its words take, for the labels drawn after it to keep clear of. `height` is the
 * pane's: target 2 off it has no dash. */
export function drawStrategy(ctx: CanvasRenderingContext2D, p: StrategyPx, width: number,
  column: readonly LabelRect[], height = Number.POSITIVE_INFINITY): LabelRect[] {
  const { s } = p;
  const live = s.state !== 'forming';
  const ink = live ? L : S;
  const measure = (font: string) => (t: string) => {
    ctx.font = font;
    return ctx.measureText(t).width;
  };
  const plain = measure(S.font);
  const bold = measure(S.nameFont);
  const top = Math.min(p.yTarget, p.yStop);
  const bottom = Math.max(p.yTarget, p.yStop);
  // Its name and window sit inside its top-left corner, or under it when the box is too short to hold two lines.
  const inside = bottom - top >= 2 * S.lineH + 2 * S.padPx;
  const nameY = inside ? top + S.padPx : bottom + S.padPx;
  const inner = columnLeft(width, nameY, nameY + 2 * S.lineH, column);
  const span = strategySpan({ after: p.xAfter + p.bar * S.gapBars, start: p.xStart, end: p.xEnd, right: width, inner,
    minText: S.minTextPx, wait: S.waitPx });
  const { x1, x2 } = span;
  const w = Math.max(1, x2 - x1);
  ctx.fillStyle = ink.riskFill;
  ctx.fillRect(x1, Math.min(p.yEntry, p.yStop), w, Math.abs(p.yStop - p.yEntry));
  ctx.fillStyle = ink.rewardFill;
  ctx.fillRect(x1, Math.min(p.yEntry, p.yTarget), w, Math.abs(p.yTarget - p.yEntry));
  ctx.lineWidth = 1;
  ctx.setLineDash(live ? [] : [3, 3]);
  ctx.strokeStyle = ink.outline;
  ctx.strokeRect(Math.round(x1) + 0.5, Math.round(top) + 0.5, Math.round(w), Math.max(1, Math.round(bottom - top)));
  ctx.setLineDash(live ? [...L.entryDash] : [3, 3]);
  ctx.lineWidth = live ? L.entryWidth : 1;
  ctx.strokeStyle = ink.entryLine;
  ctx.beginPath();
  ctx.moveTo(x1, Math.round(p.yEntry) + 0.5);
  ctx.lineTo(x2, Math.round(p.yEntry) + 0.5);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.lineWidth = 1;

  const room = Math.min(x2, inner) - x1 - 2 * S.padPx;
  const words: LabelRect[] = [];
  if (room > 0) {
    // "GAP AND GO strategy" while forming, "FLAT TOP BREAKOUT armed" after: the word is dropped before the name is
    // cut, and once armed it leads the second line instead.
    const name = fitName(s.name, room, bold);
    const nameW = bold(name);
    const tail = ` ${s.word}`;
    const tailFont = live ? S.nameFont : S.font;
    const tailW = measure(tailFont)(tail);
    const withWord = name === s.name && nameW + tailW <= room;
    const wordInk = live ? L.state[s.state as keyof typeof L.state] : S.when;
    const left = x1 + S.padPx;
    const whenText = span.waiting ? s.whenWaiting : s.when;
    const lead = live && !withWord ? fitText(s.word, room, bold) : '';
    const leadW = lead ? bold(lead) : 0;
    const gap = lead ? plain(' ') : 0;
    const when = whenText && room - leadW - gap > 0 ? fitText(whenText, room - leadW - gap, plain) : '';
    const line1W = nameW + (withWord ? tailW : 0);
    const line2W = leadW + (when ? gap + plain(when) : 0);
    if (live) {
      // Once armed its words sit on a dark backing: the entry line and the price's line run under them.
      ctx.fillStyle = L.wordBacking;
      ctx.fillRect(left - 2, nameY - 1, line1W + 4, S.lineH);
      if (line2W > 0) ctx.fillRect(left - 2, nameY + S.lineH - 1, line2W + 4, S.lineH);
    }
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.font = S.nameFont;
    ctx.fillStyle = ink.name;
    ctx.fillText(name, left, nameY);
    if (withWord) {
      ctx.font = tailFont;
      ctx.fillStyle = wordInk;
      ctx.fillText(tail, left + nameW, nameY);
    }
    if (lead) {
      ctx.font = S.nameFont;
      ctx.fillStyle = wordInk;
      ctx.fillText(lead, left, nameY + S.lineH);
    }
    if (when) {
      ctx.font = S.font;
      ctx.fillStyle = ink.when;
      ctx.fillText(when, left + leadW + gap, nameY + S.lineH);
    }
    words.push({ left, top: nameY, right: left + Math.max(line1W, line2W),
      bottom: nameY + (line2W > 0 ? 2 : 1) * S.lineH });
  }
  const y2 = s.target2 !== null ? p.yTarget2 ?? null : null;
  if (y2 !== null && y2 >= 0 && y2 <= height) {
    // In view: a dotted dash across the box at its price. Its name is the edge column's ("T2 4.49", `strategyWords`),
    // where a level at its price folds in; off the pane the column's tag says it (2026-10-13).
    ctx.setLineDash([...S.target2Dash]);
    ctx.strokeStyle = ink.target2Ink;
    ctx.beginPath();
    ctx.moveTo(x1, Math.round(y2) + 0.5);
    ctx.lineTo(x2, Math.round(y2) + 0.5);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  return words;
}
