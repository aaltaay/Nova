/** Tests only: a fake chart, series and canvas for Ahead's primitives, and a made-up scene (Nova Marketing Sample
 * Data shapes; the numbers mean nothing). */
import { vi } from 'vitest';
import type { IChartApi, SeriesAttachedParameter, SeriesType, Time } from 'lightweight-charts';
import type { AheadScene, SceneBand } from './aheadSceneTypes';

export const T0 = 1_792_486_800;
export const TIMES = Array.from({ length: 10 }, (_, i) => T0 + i * 60);
export const ANCHOR_T = TIMES[9];
export const X = (logical: number) => 100 + logical * 10;
export const Y = (p: number) => 1100 - p * 200;

export function fakeChart(opts: { paneHeight?: number; scaleTop?: number } = {}) {
  const ts = {
    timeToIndex: (t: Time) => {
      const i = TIMES.indexOf(Number(t));
      return i < 0 ? null : i;
    },
    logicalToCoordinate: (l: number) => X(l),
    options: () => ({ barSpacing: 10 }),
    height: () => 26,
  };
  const chart = { timeScale: () => ts, paneSize: () => ({ width: 600, height: opts.paneHeight ?? 400 }) };
  const series = {
    dataByIndex: (i: number) => (i >= 0 && i < TIMES.length ? { time: TIMES[i], close: 5, value: 0.02 } : null),
    priceToCoordinate: (p: number) => Y(p),
    priceScale: () => ({ options: () => ({ scaleMargins: { top: opts.scaleTop ?? 0.8, bottom: 0 } }) }),
    setData: vi.fn(),
    update: vi.fn(),
  };
  const requestUpdate = vi.fn();
  const param = { chart, series, requestUpdate } as unknown as SeriesAttachedParameter<Time, SeriesType>;
  return { chart: chart as unknown as IChartApi, series, requestUpdate, param };
}

export function fakeCtx() {
  return {
    save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(), closePath: vi.fn(), rect: vi.fn(), clip: vi.fn(),
    fillRect: vi.fn(), strokeRect: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fill: vi.fn(),
    arc: vi.fn(), setLineDash: vi.fn(), roundRect: vi.fn(), fillText: vi.fn(),
    measureText: (text: string) => ({ width: text.length * 6 }),
    font: '', fillStyle: '', strokeStyle: '', lineWidth: 0, globalAlpha: 1, lineCap: '', textAlign: '',
    textBaseline: '',
  };
}

export type FakeCtx = ReturnType<typeof fakeCtx>;

/** Paint one renderer on a fake canvas `width` x `height`, as lightweight-charts would. */
export function paint(renderer: { draw: (target: never) => void }, width = 600, height = 400,
  prepare?: (ctx: FakeCtx) => void): FakeCtx {
  const ctx = fakeCtx();
  prepare?.(ctx);
  const target = {
    useMediaCoordinateSpace: (draw: (scope: unknown) => void) => draw({ context: ctx, mediaSize: { width, height } }),
  };
  renderer.draw(target as never);
  return ctx;
}

const band = (k: number): SceneBand => ({ k, q10: 4.9 - k * 0.01, q25: 4.95, q50: 5, q75: 5.05, q90: 5.1 + k * 0.01 });

export function sampleScene(over: Partial<AheadScene> = {}): AheadScene {
  return {
    on: true,
    anchorT: ANCHOR_T,
    horizon: 15,
    zone: { title: 'AHEAD · next 15 min', tags: [{ text: 'AI view, not data', fg: '#c7d2fe', bg: '#222' }],
      nowText: 'now 09:10' },
    ticks: [{ k: 5, text: '09:15' }, { k: 10, text: '09:20' }, { k: 15, text: '09:25' }],
    fan: Array.from({ length: 15 }, (_, i) => band(i + 1)),
    paths: [{ points: Array.from({ length: 15 }, () => 5.02), color: '#c7d2fe', alpha: 0.34 }],
    lines: [
      { kind: 'support', fromP: 4.9, slope: 0.01, toSteps: 8, color: '#34d399' },
      { kind: 'resistance', fromP: 5.1, slope: -0.015, toSteps: 8, color: '#ff9f43' },
    ],
    meet: { steps: 8, p: 4.98, text: 'lines meet ≈ 09:18', inZone: true },
    hLines: [{ p: 5.2, color: '#f0876f', dash: [], chip: '' }],
    chips: [
      { p: 5.2, text: '▲ 5.20 first · 27% (forecast)', color: '#f0876f' },
      { p: 5.19, text: 'neither in 15 min · 30% (forecast)', color: '#8b92a5' },
    ],
    keepInView: { lo: 4.75, hi: 5.25 },
    ghostVolume: Array.from({ length: 15 }, (_, i) => ({ k: i + 1, q10: 1, q50: 2, q90: 3 })),
    macd: Array.from({ length: 15 }, (_, i) => band(i + 1)),
    words: [],
    legend: "Nova's lines carried on · 16 of 200 possible paths",
    lineRead: null,
    walls: null,
    triggers: null,
    ...over,
  };
}
