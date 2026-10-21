import { describe, expect, it } from 'vitest';
import { AheadVolumePrimitive } from './AheadVolumePrimitive';
import { X, fakeChart, paint, sampleScene } from './aheadTestKit';

function attach(ghost = sampleScene().ghostVolume) {
  const f = fakeChart({ paneHeight: 400, scaleTop: 0.8 });
  // Volume on its own overlay scale: 0 at the pane's bottom, 20 px a share.
  f.series.priceToCoordinate = (v: number) => 400 - v * 20;
  const p = new AheadVolumePrimitive();
  p.attached(f.param);
  p.setScene(sampleScene({ ghostVolume: ghost }), 'AI volume');
  p.updateAllViews();
  return { ...f, p, view: p.paneViews()[0] };
}

describe('AheadVolumePrimitive', () => {
  it('puts a ghost bar on each forecast minute, from the volume base', () => {
    const { p } = attach();
    expect(p.px?.bars).toHaveLength(15);
    expect(p.px?.bars[0]).toEqual({ x: X(10), yBase: 400, y10: 380, y50: 360, y90: 340 });
    expect(p.px?.bandTop).toBe(320);
    expect(p.px?.left).toBe(X(9) + 5);
  });

  it('never rescales the volume: no autoscale, nothing set on the series', () => {
    const { p, series, view } = attach();
    expect('autoscaleInfo' in p).toBe(false);
    paint(view.renderer() as never);
    expect(series.setData).not.toHaveBeenCalled();
    expect(series.update).not.toHaveBeenCalled();
  });

  it('draws an outline to q50 and a whisker q10-q90, and labels them', () => {
    const { view } = attach();
    const ctx = paint(view.renderer() as never);
    expect(ctx.strokeRect).toHaveBeenCalledWith(X(10) - 3.1, 360, 6.2, 40);
    expect(ctx.moveTo).toHaveBeenCalledWith(X(10), 340);
    expect(ctx.lineTo).toHaveBeenCalledWith(X(10), 380);
    expect(ctx.fillText).toHaveBeenCalledWith('AI volume', X(9) + 5 + 8, 332);
  });

  it('clips a ghost taller than the volume band at its top, with a caret', () => {
    const tall = Array.from({ length: 15 }, (_, i) => ({ k: i + 1, q10: 1, q50: 2, q90: i === 0 ? 5 : 3 }));
    const { view } = attach(tall);
    const ctx = paint(view.renderer() as never);
    expect(ctx.moveTo).toHaveBeenCalledWith(X(10), 320);
    // The caret: up to the band's top and down again.
    expect(ctx.lineTo).toHaveBeenCalledWith(X(10), 320);
    expect(ctx.lineTo).toHaveBeenCalledWith(X(10) + 3, 323);
  });

  it('draws nothing while the AI view is not shown', () => {
    const { p, view } = attach(null);
    expect(p.px).toBeNull();
    expect(paint(view.renderer() as never).strokeRect).not.toHaveBeenCalled();
  });
});
