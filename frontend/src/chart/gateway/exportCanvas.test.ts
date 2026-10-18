/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { IChartApi, Time } from 'lightweight-charts';
import { isoToEtTime, type RawBar } from '../../tickerChartData';
import { annotationColor, annotationSummary } from './annotations';
import { drawCausalOverlay, exportGallery, paneImage, type Pane } from './exportCanvas';
import type { Entry, Gallery } from './types';

const sha = 'a'.repeat(64);
const bar = (minute: number): RawBar => ({ t: `2022-02-10T15:${String(minute).padStart(2, '0')}:00Z`, o: 2, h: 3, l: 1, c: 2.5, v: 100 });
const entry = (): Entry => ({ id: 0, symbol: 'EXAMPLE', date: '2022-02-10', annotations: [],
  bars_1m: [bar(0), bar(5)], bars_5m: [bar(0), bar(5)], source: { selection_sha256: sha, projection_sha256: sha } });

function context(canvas: HTMLCanvasElement) {
  return { canvas, fillRect: vi.fn(), drawImage: vi.fn(), fillText: vi.fn(), setLineDash: vi.fn(),
    beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(),
    measureText: (text: string) => ({ width: text.length * 8 }),
  } as unknown as CanvasRenderingContext2D;
}

function pane(value: Entry, timeframe: '1Min' | '5Min' = '1Min'): Pane {
  const native = document.createElement('canvas'); native.width = 600; native.height = 380;
  const data = timeframe === '1Min' ? value.bars_1m : value.bars_5m;
  const scale = { fitContent: vi.fn(), options: () => ({ barSpacing: 10 }), timeToCoordinate: (time: Time) => {
    const index = data.findIndex(raw => isoToEtTime(raw.t, false) === time);
    return index < 0 ? null : 20 + index * 10;
  } };
  return { entry: value, timeframe, chart: {
    timeScale: () => scale, priceScale: () => ({ width: () => 50 }),
    chartElement: () => ({ clientWidth: 600, clientHeight: 380 }),
    resize: vi.fn((width: number, height: number) => { native.width = width; native.height = height; }),
    takeScreenshot: vi.fn(() => native),
  } as unknown as IChartApi };
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    return context(this);
  } as typeof HTMLCanvasElement.prototype.getContext);
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,EXAMPLE');
});
afterEach(() => vi.restoreAllMocks());

describe('generic native chart annotations', () => {
  it('draws neither amber context nor an as-of marker for whole-session views', () => {
    const canvas = document.createElement('canvas'); canvas.width = 500;
    const ctx = context(canvas);
    drawCausalOverlay(pane(entry()), ctx, 500, 380);
    expect(ctx.fillRect).not.toHaveBeenCalled();
    expect(ctx.stroke).not.toHaveBeenCalled();
  });
  it('keeps the entire crossing 5-minute candle contextual', () => {
    const canvas = document.createElement('canvas'); canvas.width = 500;
    const ctx = context(canvas);
    drawCausalOverlay(pane({ ...entry(), as_of_m: 601, as_of_t: '2022-02-10T15:01:00Z' }, '5Min'), ctx, 500, 380);
    expect(ctx.fillRect).toHaveBeenCalledWith(15, 0, 435, 380);
    expect(ctx.fillText).toHaveBeenCalledWith('As of 10:01', expect.any(Number), expect.any(Number));
  });
  it('draws a time marker only at an available native coordinate', () => {
    const value = entry(); value.annotations = [{ kind: 'time_marker', minute: 600, label: 'Observation', color: 'red' }];
    const canvas = document.createElement('canvas'); canvas.width = 500;
    const ctx = context(canvas);
    drawCausalOverlay(pane(value), ctx, 500, 380);
    expect(ctx.moveTo).toHaveBeenCalledWith(20, 0);
    expect(ctx.fillText).toHaveBeenCalledWith('Observation', 24, 35);
    expect(ctx.strokeStyle).toBe('#ef4444');
    expect(ctx.fillRect).not.toHaveBeenCalled();
  });
  it('retains missing-coordinate annotations in text without inventing a candle', () => {
    const value = entry(); value.annotations = [{ kind: 'time_marker', minute: 603, label: 'Observation' }];
    const canvas = document.createElement('canvas'); canvas.width = 500;
    const ctx = context(canvas);
    drawCausalOverlay(pane(value, '5Min'), ctx, 500, 380);
    expect(ctx.stroke).not.toHaveBeenCalled();
    expect(annotationSummary(value.annotations)).toBe('Observation: 10:03 ET');
    expect(value.bars_5m).toHaveLength(2);
  });
  it('uses the fixed palette with blue as the default', () => {
    expect(annotationColor()).toBe('#4da8ff');
    expect(annotationColor('green')).toBe('#10b981');
    expect(annotationColor('grey')).toBe('#a2aab8');
  });
});

describe('generic native PNG composition', () => {
  it('captures the existing native chart and restores its dimensions', () => {
    const value = pane(entry());
    paneImage(value, 470, 535);
    expect(value.chart.takeScreenshot).toHaveBeenCalledOnce();
    expect(value.chart.resize).toHaveBeenNthCalledWith(1, 470, 535, true);
    expect(value.chart.resize).toHaveBeenLastCalledWith(600, 380, true);
  });
  it('restores dimensions even when native capture fails', () => {
    const value = pane(entry());
    vi.mocked(value.chart.takeScreenshot).mockImplementation(() => { throw new Error('capture failed'); });
    expect(() => paneImage(value, 470, 535)).toThrow('capture failed');
    expect(value.chart.resize).toHaveBeenLastCalledWith(600, 380, true);
  });
  it('exports repeated tickers and all generic annotation captions from native panes', () => {
    const first = entry();
    first.annotations = Array.from({ length: 32 }, (_, i) => ({ kind: 'time_marker', minute: 600 + i, label: `Observation${i}` }));
    const second = { ...entry(), id: 1, date: '2022-02-11' };
    const gallery: Gallery = { schema_version: 1, kind: 'historical_ohlcv', family: 'Historical review',
      selection_sha256: sha, entries: [first, second], timings: { load_ms: 1, aggregation_ms: 2 } };
    const panes = new Map<string, Pane>();
    for (const value of gallery.entries) for (const timeframe of ['1Min', '5Min'] as const) panes.set(`${value.id}:${timeframe}`, pane(value, timeframe));
    const contexts: CanvasRenderingContext2D[] = [];
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockImplementation(function (this: HTMLCanvasElement) {
      const ctx = context(this); contexts.push(ctx); return ctx;
    } as typeof HTMLCanvasElement.prototype.getContext);
    expect(exportGallery(gallery, panes)).toBe('data:image/png;base64,EXAMPLE');
    const text = vi.mocked(contexts[0].fillText).mock.calls.map(call => call[0]).join(' ');
    expect(text).toContain('2 historical OHLCV entries');
    expect(text).toContain('Observation31: 10:31 ET');
    expect(text).toContain(`Selection SHA256 ${sha}`);
    for (const value of panes.values()) expect(value.chart.takeScreenshot).toHaveBeenCalledOnce();
  });
});
