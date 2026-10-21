import type { Logical } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { paneWords, publishPaneWords } from '../chart';
import { AHEAD_WORDS_SOURCE, AheadPrimitive, edgeInset } from './AheadPrimitive';
import { AHEAD_DRAW } from './aheadCanvas';
import { ANCHOR_T, X, Y, fakeChart, paint, sampleScene } from './aheadTestKit';

function attach(scene = sampleScene()) {
  const f = fakeChart();
  const p = new AheadPrimitive();
  p.attached(f.param);
  p.setScene(scene);
  p.updateAllViews();
  const [under, over] = p.paneViews();
  return { ...f, p, under, over };
}

const nextMicrotask = () => new Promise<void>(resolve => queueMicrotask(resolve));

describe('AheadPrimitive', () => {
  it('puts step k at logicalToCoordinate(index of the anchor + k), the zone right of the anchor candle', () => {
    const { p } = attach();
    const px = p.px;
    expect(px).not.toBeNull();
    expect(px?.anchor).toEqual({ x: X(9), y: Y(5) });
    for (const k of [1, 7, 15]) expect(px?.xs.get(k)).toBe(X(9 + k));
    expect(px?.left).toBe(X(9) + 5);
    expect(px?.right).toBe(X(9 + 15) + 5);
    expect(p.stepX(2.5)).toBe(X(11.5));
  });

  it('hatches the zone, draws the fan from the anchor candle and the paths, under the candles', () => {
    const { under } = attach();
    expect(under.zOrder?.()).toBe('bottom');
    const ctx = paint(under.renderer() as never);
    expect(ctx.fillRect).toHaveBeenCalledWith(X(9) + 5, 0, X(24) + 5 - (X(9) + 5), 400);
    // Two bands, each starting at the anchor candle's close.
    expect(ctx.fill).toHaveBeenCalledTimes(2);
    expect(ctx.moveTo).toHaveBeenCalledWith(X(9), Y(5));
    expect(ctx.lineTo).toHaveBeenCalledWith(X(10), Y(5.02));
  });

  it('stops the zone at the stock read word column at the right edge', () => {
    const { chart, under } = attach();
    // Words away from the edge do not count; the column at the edge does.
    publishPaneWords(chart, 'stock-read', [{ left: 340, top: 10, right: 587, bottom: 24 }, { left: 10, top: 0,
      right: 60, bottom: 14 }]);
    expect(edgeInset(chart, 600)).toBe(260);
    const ctx = paint(under.renderer() as never);
    expect(ctx.rect).toHaveBeenCalledWith(0, 0, 340, 400);
    // The column never takes more than 45% of the pane.
    publishPaneWords(chart, 'stock-read', [{ left: 100, top: 10, right: 587, bottom: 24 }]);
    expect(edgeInset(chart, 600)).toBe(270);
    publishPaneWords(chart, 'stock-read', []);
    expect(edgeInset(chart, 600)).toBe(0);
  });

  it('draws the lines to the meet, the ring, the stubs, the chips, the minute labels and "now"', () => {
    const { over, chart } = attach();
    expect(over.zOrder?.()).toBe('top');
    const ctx = paint(over.renderer() as never);
    const texts = ctx.fillText.mock.calls.map(c => c[0]);
    expect(texts).toEqual(expect.arrayContaining(['lines meet ≈ 09:18', '▲ 5.20 first · 27% (forecast)',
      'neither in 15 min · 30% (forecast)', '09:15', '09:20', 'now 09:10']));
    // The 09:25 label sits on the zone's very edge: left out rather than cut.
    expect(texts).not.toContain('09:25');
    expect(ctx.arc).toHaveBeenCalledWith(X(17), Y(4.98), 6, 0, Math.PI * 2);
    expect(ctx.setLineDash).toHaveBeenCalledWith([2, 5]);
    expect(paneWords(chart).rects.length).toBeGreaterThan(0);
  });

  it('keeps chips that would sit on each other apart', () => {
    const { over } = attach();
    const ctx = paint(over.renderer() as never);
    const ys = ctx.fillText.mock.calls.filter(c => String(c[0]).includes('first') || String(c[0]).includes('neither'))
      .map(c => c[2] as number);
    expect(ys).toHaveLength(2);
    expect(Math.abs(ys[0] - ys[1])).toBeGreaterThanOrEqual(18);
  });

  it('tells the heading where the zone went, once per move of a pixel or more', () => {
    const { p, over } = attach();
    const cb = vi.fn();
    p.setLayoutListener(cb);
    cb.mockClear();
    paint(over.renderer() as never);
    expect(cb).toHaveBeenCalledWith({ left: X(9) + 5, right: X(24) + 5, top: 0 });
    paint(over.renderer() as never);
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('keeps on the price scale only what it draws, and only once the zone is in view', () => {
    const { p, over } = attach();
    // Before the zone has been drawn there is nothing on screen to keep in view.
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
    paint(over.renderer() as never);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toEqual({ priceRange: { minValue: 4.75, maxValue: 5.25 } });
    expect(p.autoscaleInfo(0 as Logical, 5 as Logical)).toBeNull();
    p.setScene(sampleScene({ keepInView: null }));
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
    p.setScene(sampleScene({ on: false }));
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
  });

  it('stretches no price scale for a zone the word column clipped to nothing', () => {
    const { p, over, chart } = attach();
    paint(over.renderer() as never);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).not.toBeNull();
    // On a narrow pane the column (capped at 45% of it) reaches left of the anchor candle: no room at all.
    publishPaneWords(chart, 'stock-read', [{ left: 150, top: 10, right: 295, bottom: 24 }]);
    paint(over.renderer() as never, 300, 400);
    expect(p.autoscaleInfo(0 as Logical, 20 as Logical)).toBeNull();
    publishPaneWords(chart, 'stock-read', []);
  });

  it("does not count its own chips as the word column (no repaint loop)", async () => {
    const { chart, over, requestUpdate } = attach();
    paint(over.renderer() as never);
    // Ahead's chips sit at the zone's right edge, inside the column's slack: they must not move its own clip.
    publishPaneWords(chart, AHEAD_WORDS_SOURCE, [{ left: 500, top: 10, right: 596, bottom: 24 }]);
    expect(edgeInset(chart, 600)).toBe(0);
    paint(over.renderer() as never);
    await nextMicrotask();
    requestUpdate.mockClear();
    paint(over.renderer() as never);
    await nextMicrotask();
    expect(requestUpdate).not.toHaveBeenCalled();
  });

  it('draws nothing, and takes its words back, with Ahead off or no anchor on the pane', async () => {
    const { p, over, chart } = attach();
    paint(over.renderer() as never);
    p.setScene(sampleScene({ on: false }));
    p.updateAllViews();
    expect(p.px).toBeNull();
    const ctx = paint(over.renderer() as never);
    expect(ctx.fillText).not.toHaveBeenCalled();
    await nextMicrotask();
    p.setScene(sampleScene({ anchorT: ANCHOR_T + 3600 }));
    p.updateAllViews();
    expect(p.px).toBeNull();
    p.detached();
    expect(paneWords(chart).rects).toEqual([]);
  });

  it('never adds anything to the series', () => {
    const { series, over, under } = attach();
    paint(under.renderer() as never);
    paint(over.renderer() as never);
    expect(series.setData).not.toHaveBeenCalled();
    expect(series.update).not.toHaveBeenCalled();
  });

  it('dims the fan on a strategy scope', () => {
    const fillAlphas = (dim: boolean) => {
      const { p, under } = attach();
      p.setScene(sampleScene(), dim);
      p.updateAllViews();
      const seen: number[] = [];
      paint(under.renderer() as never, 600, 400, ctx => ctx.fill.mockImplementation(() => seen.push(ctx.globalAlpha)));
      return seen;
    };
    expect(fillAlphas(false)).toEqual([AHEAD_DRAW.fanOuter, AHEAD_DRAW.fanInner]);
    expect(fillAlphas(true)).toEqual([AHEAD_DRAW.fanOuter * AHEAD_DRAW.fanDim, AHEAD_DRAW.fanInner * AHEAD_DRAW.fanDim]);
    expect(AHEAD_WORDS_SOURCE).toBe('ahead');
  });
});
