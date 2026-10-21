import { describe, expect, it } from 'vitest';
import { AheadMacdPrimitive } from './AheadMacdPrimitive';
import { ANCHOR_T, X, fakeChart, paint, sampleScene } from './aheadTestKit';

function attach(withBands = true) {
  const f = fakeChart();
  f.series.priceToCoordinate = (v: number) => 200 - v * 1000;
  const p = new AheadMacdPrimitive();
  p.attached(f.param);
  p.setFan({ anchorT: ANCHOR_T, horizon: 15, bands: withBands ? sampleScene().macd : null, caption: 'MACD worked out' });
  p.updateAllViews();
  const [under, over] = p.paneViews();
  return { ...f, p, under, over };
}

describe('AheadMacdPrimitive', () => {
  it('starts the fan at the last real MACD point and steps it on the same bar positions as the price pane', () => {
    const { p } = attach();
    expect(p.px?.from).toEqual({ x: X(9), y: 200 - 0.02 * 1000 });
    expect(p.px?.xs[0]).toBe(X(10));
    expect(p.px?.xs).toHaveLength(15);
  });

  it('hatches the zone under the lines and draws two bands and the caption over them', () => {
    const { under, over } = attach();
    expect(under.zOrder?.()).toBe('bottom');
    expect(paint(under.renderer() as never).fillRect).toHaveBeenCalled();
    const ctx = paint(over.renderer() as never);
    expect(ctx.fill).toHaveBeenCalledTimes(2);
    expect(ctx.fillText).toHaveBeenCalledWith('MACD worked out', X(9) + 5 + 8, 14);
  });

  it('draws nothing without a fan, never touching the series', () => {
    const { p, over, series } = attach(false);
    expect(p.px).toBeNull();
    expect(paint(over.renderer() as never).fill).not.toHaveBeenCalled();
    p.setFan(null);
    p.updateAllViews();
    expect(p.px).toBeNull();
    expect(series.setData).not.toHaveBeenCalled();
  });
});
