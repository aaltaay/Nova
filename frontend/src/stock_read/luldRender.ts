/**
 * Drawing Nova's LULD band on the 1-minute and 10-second charts (ADR 047 amendments), once `SetupShapesPrimitive` has put
 * its steps in pixels: the upper and the lower band each a line that steps where the band moved -- solid where the
 * band was exact, dashed where it was approximate -- and nothing where there was none (a halt). Its names are the edge
 * column's (`luldShapes.luldWords`).
 */
import type { SceneLuldStep } from './sceneTypes';

/** A step in pixels: from `x1` to `x2`, each band's height (null: no such band, or off the price scale). */
export interface LuldStepPx {
  x1: number;
  x2: number;
  yLower: number | null;
  yUpper: number | null;
  s: SceneLuldStep;
}

export interface LuldPx {
  steps: LuldStepPx[];
  color: string;
}

const LINE_PX = 1.5;
const APPROX_DASH = [5, 3];

/** One band's line: each step flat at its height, joined to the next where the two touch. */
function drawBand(ctx: CanvasRenderingContext2D, steps: LuldStepPx[], y: (p: LuldStepPx) => number | null): void {
  for (let k = 0; k < steps.length; k += 1) {
    const p = steps[k];
    const yy = y(p);
    if (yy === null) continue;
    ctx.setLineDash(p.s.approx ? APPROX_DASH : []);
    ctx.beginPath();
    ctx.moveTo(p.x1, yy);
    ctx.lineTo(p.x2, yy);
    const next = steps[k + 1];
    const yn = next ? y(next) : null;
    // The riser where the band moved: only between steps that meet (a halt between them leaves a gap).
    if (next && yn !== null && Math.abs(next.x1 - p.x2) < 0.5) ctx.lineTo(next.x1, yn);
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

export function drawLuld(ctx: CanvasRenderingContext2D, px: LuldPx): void {
  ctx.strokeStyle = px.color;
  ctx.lineWidth = LINE_PX;
  drawBand(ctx, px.steps, p => p.yUpper);
  drawBand(ctx, px.steps, p => p.yLower);
  ctx.lineWidth = 1;
}
