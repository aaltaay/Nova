/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi } from 'vitest';
import type { IChartApi } from 'lightweight-charts';
import { keepTimeAxisLabelsWhole, timeAxisLabelFits } from './timeAxisEdgeLabels';

/** The chart's DOM as lightweight-charts builds it: a pane row, then the time-axis row. */
function fakeChart(canvasWidth: number, ratio: number) {
  const root = document.createElement('div');
  root.innerHTML = '<table><tr><td></td><td><canvas></canvas></td><td></td></tr>'
    + '<tr><td></td><td><div><canvas></canvas><canvas></canvas></div></td><td></td></tr></table>';
  const canvas = root.querySelectorAll('canvas')[1];
  canvas.width = canvasWidth;
  const paint = vi.fn();
  const ctx = {
    textAlign: 'center',
    fillText: paint,
    getTransform: () => ({ a: ratio }),
    measureText: (text: string) => ({ width: text.length * 6 }),
  };
  canvas.getContext = (() => ctx) as unknown as typeof canvas.getContext;
  const chart = { chartElement: () => root } as unknown as IChartApi;
  return { chart, ctx, paint };
}

describe('timeAxisLabelFits', () => {
  it('fits a centred label wholly inside the axis, with half a pixel of slack', () => {
    expect(timeAxisLabelFits(50, 48, 300)).toBe(true);
    expect(timeAxisLabelFits(24, 48, 300)).toBe(true);
    expect(timeAxisLabelFits(23.4, 48, 300)).toBe(false);
    expect(timeAxisLabelFits(276, 48, 300)).toBe(true);
    expect(timeAxisLabelFits(276.6, 48, 300)).toBe(false);
  });
});

describe('keepTimeAxisLabelsWhole', () => {
  it('leaves out a tick label that would cross either edge and draws the rest', () => {
    // 600 bitmap px at DPR 1.5 is a 400 px axis; "10:00 AM" measures 48 px.
    const { chart, ctx, paint } = fakeChart(600, 1.5);
    keepTimeAxisLabelsWhole(chart);
    ctx.fillText('10:00 AM', 10, 12);
    ctx.fillText('10:00 AM', 200, 12);
    ctx.fillText('10:00 AM', 390, 12);
    expect(paint.mock.calls).toEqual([['10:00 AM', 200, 12]]);
  });

  it('leaves text that is not a centred tick label alone, and undoes itself', () => {
    const { chart, ctx, paint } = fakeChart(400, 1);
    const undo = keepTimeAxisLabelsWhole(chart);
    ctx.textAlign = 'left';
    ctx.fillText('label', -5, 12, 30);
    expect(paint.mock.calls).toEqual([['label', -5, 12, 30]]);
    undo();
    expect(Object.prototype.hasOwnProperty.call(ctx, 'fillText')).toBe(false);
  });
});
