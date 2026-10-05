import type { IChartApi } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';
import { paneWords, publishPaneWords, subscribePaneWords } from './paneWords';

const chartOf = () => ({}) as unknown as IChartApi;
const rect = (left: number, top = 0) => ({ left, top, right: left + 20, bottom: top + 14 });
const nextMicrotask = () => new Promise<void>(resolve => queueMicrotask(resolve));

describe('paneWords', () => {
  it("holds every source's words and replaces one source whole", () => {
    const chart = chartOf();
    publishPaneWords(chart, 'labels', [rect(10), rect(40)]);
    publishPaneWords(chart, 'fills', [rect(90)]);
    expect(paneWords(chart).rects).toHaveLength(3);
    publishPaneWords(chart, 'labels', [rect(10)]);
    expect(paneWords(chart).rects.map(r => r.left)).toEqual([10, 90]);
    publishPaneWords(chart, 'labels', []);
    expect(paneWords(chart).rects.map(r => r.left)).toEqual([90]);
  });

  it('keeps charts apart and answers nothing for one nobody wrote on', () => {
    const a = chartOf();
    const b = chartOf();
    publishPaneWords(a, 'labels', [rect(10)]);
    expect(paneWords(b).rects).toEqual([]);
    expect(paneWords(null).rects).toEqual([]);
  });

  it('changes its version only when the words change', () => {
    const chart = chartOf();
    publishPaneWords(chart, 'labels', [rect(10)]);
    const v1 = paneWords(chart).version;
    publishPaneWords(chart, 'labels', [rect(10)]);
    publishPaneWords(chart, 'labels', [rect(10.04)]); // float noise under a tenth of a pixel is not a move
    expect(paneWords(chart).version).toBe(v1);
    expect(paneWords(chart)).toBe(paneWords(chart));
    publishPaneWords(chart, 'labels', [rect(11)]);
    expect(paneWords(chart).version).toBeGreaterThan(v1);
  });

  it('takes back nothing it never held without a change', () => {
    const chart = chartOf();
    publishPaneWords(chart, 'labels', []);
    expect(paneWords(chart).version).toBe(0);
  });

  it('announces a change once, after the paint that made it', async () => {
    const chart = chartOf();
    const heard = vi.fn();
    const stop = subscribePaneWords(chart, heard);
    publishPaneWords(chart, 'labels', [rect(10)]);
    publishPaneWords(chart, 'fills', [rect(50)]);
    expect(heard).not.toHaveBeenCalled();
    await nextMicrotask();
    expect(heard).toHaveBeenCalledTimes(1);
    stop();
    publishPaneWords(chart, 'labels', [rect(70)]);
    await nextMicrotask();
    expect(heard).toHaveBeenCalledTimes(1);
  });
});
