import type { Time } from 'lightweight-charts';
import { describe, expect, it } from 'vitest';
import { drawLuld, type LuldStepPx } from './luldRender';
import type { SceneLuldStep } from './sceneTypes';

/** A canvas that writes down each stroked path and the dash it was stroked with. */
function recorder() {
  const paths: { dash: number[]; points: [number, number][] }[] = [];
  let points: [number, number][] = [];
  let dash: number[] = [];
  const ctx = {
    strokeStyle: '', lineWidth: 1,
    setLineDash: (d: number[]) => { dash = d; },
    beginPath: () => { points = []; },
    moveTo: (x: number, y: number) => { points.push([x, y]); },
    lineTo: (x: number, y: number) => { points.push([x, y]); },
    stroke: () => { paths.push({ dash, points }); },
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, paths };
}

const S = (approx = false): SceneLuldStep => ({ from: { t: 0 as Time, frac: 0 }, to: { t: 0 as Time, frac: 0 },
  lower: 1, upper: 2, approx });
const step = (x1: number, x2: number, yUpper: number | null, approx = false): LuldStepPx =>
  ({ x1, x2, yUpper, yLower: null, s: S(approx) });

describe('drawLuld', () => {
  it('steps the line where the band moved and leaves a halt open', () => {
    const { ctx, paths } = recorder();
    drawLuld(ctx, { color: '#f43f5e', steps: [step(10, 40, 100), step(40, 70, 90), step(90, 120, 80)] });
    expect(paths.map(p => p.points)).toEqual([
      [[10, 100], [40, 100], [40, 90]],   // flat, then the riser to the next band
      [[40, 90], [70, 90]],               // a halt from 70 to 90: no riser across it
      [[90, 80], [120, 80]],
    ]);
  });

  it('dashes an approximate stretch and skips a band off the scale', () => {
    const { ctx, paths } = recorder();
    drawLuld(ctx, { color: '#f43f5e', steps: [step(10, 40, null), step(40, 70, 90, true)] });
    expect(paths).toEqual([{ dash: [5, 3], points: [[40, 90], [70, 90]] }]);
  });
});
