/**
 * Placing and drawing a forming setup's strategy box on the 1-minute pane (`strategyBox.ts` decides it, operator ask
 * 2026-10-12). The box runs to the pane's right edge, under the edge column, whose words name its prices (T1, entry,
 * stop: `strategyWords`). It stands on the setup's window -- from its start, never before the newest candle -- when
 * that leaves room for its name left of the column's words; else it waits at the right edge saying when it starts.
 * Faint and dashed throughout: a plan no setup has armed. Drawn before the column, so the column's words read over it.
 */
import { STRATEGY_BOX as S } from './constants';
import { fitText } from './levelRender';
import { fmtPx } from './planMath';
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
  s: SceneStrategy;
}

export interface StrategySpan {
  x1: number;
  x2: number;
  /** Not on its window: at the right edge, waiting for it. */
  waiting: boolean;
}

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

/** Draws the box; returns the room its words take, for the labels drawn after it to keep clear of. */
export function drawStrategy(ctx: CanvasRenderingContext2D, p: StrategyPx, width: number,
  column: readonly LabelRect[]): LabelRect[] {
  const { s } = p;
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
  ctx.fillStyle = S.riskFill;
  ctx.fillRect(x1, Math.min(p.yEntry, p.yStop), w, Math.abs(p.yStop - p.yEntry));
  ctx.fillStyle = S.rewardFill;
  ctx.fillRect(x1, Math.min(p.yEntry, p.yTarget), w, Math.abs(p.yTarget - p.yEntry));
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.strokeStyle = S.outline;
  ctx.strokeRect(Math.round(x1) + 0.5, Math.round(top) + 0.5, Math.round(w), Math.max(1, Math.round(bottom - top)));
  ctx.strokeStyle = S.entryLine;
  ctx.beginPath();
  ctx.moveTo(x1, Math.round(p.yEntry) + 0.5);
  ctx.lineTo(x2, Math.round(p.yEntry) + 0.5);
  ctx.stroke();
  ctx.setLineDash([]);

  const room = Math.min(x2, inner) - x1 - 2 * S.padPx;
  const words: LabelRect[] = [];
  if (room > 0) {
    // "GAP AND GO strategy", the word dropped before the name is cut.
    const name = fitText(s.name, room, bold);
    const nameW = bold(name);
    const tail = ` ${s.word}`;
    const withWord = name === s.name && nameW + plain(tail) <= room;
    const left = x1 + S.padPx;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.font = S.nameFont;
    ctx.fillStyle = S.name;
    ctx.fillText(name, left, nameY);
    if (withWord) {
      ctx.font = S.font;
      ctx.fillStyle = S.when;
      ctx.fillText(tail, left + nameW, nameY);
    }
    let right = left + nameW + (withWord ? plain(tail) : 0);
    const whenText = span.waiting ? s.whenWaiting : s.when;
    if (whenText) {
      const when = fitText(whenText, room, plain);
      ctx.font = S.font;
      ctx.fillStyle = S.when;
      ctx.fillText(when, left, nameY + S.lineH);
      right = Math.max(right, left + plain(when));
    }
    words.push({ left, top: nameY, right, bottom: nameY + (whenText ? 2 : 1) * S.lineH });
  }
  // Target 2 past target 1: an arrow over the box (under it on a short), never a line across the pane.
  if (s.target2 !== null) {
    const long = s.side === 'long';
    const text = `${long ? '↑' : '↓'} T2 ${fmtPx(s.target2)}`;
    const y = long ? top - S.padPx - S.lineH / 2 : bottom + S.padPx + S.lineH / 2 + (inside ? 0 : 2 * S.lineH);
    ctx.font = S.font;
    ctx.textBaseline = 'middle';
    ctx.fillStyle = S.target2Ink;
    ctx.fillText(text, x1, y);
    words.push({ left: x1, top: y - S.lineH / 2, right: x1 + plain(text), bottom: y + S.lineH / 2 });
  }
  return words;
}
