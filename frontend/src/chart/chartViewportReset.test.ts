import { describe, expect, it, vi } from 'vitest';
import type { IChartApi } from 'lightweight-charts';
import { resetChartViewport } from './chartViewportReset';

function fakeChart() {
  const applyOptions = vi.fn();
  const setVisibleLogicalRange = vi.fn();
  const fitContent = vi.fn();
  const chart = {
    priceScale: () => ({ applyOptions }),
    timeScale: () => ({ setVisibleLogicalRange, fitContent }),
  } as unknown as IChartApi;
  return { chart, applyOptions, setVisibleLogicalRange, fitContent };
}

describe('resetChartViewport', () => {
  it('re-enables price autoscale and restores the pinned intraday window', () => {
    const { chart, applyOptions, setVisibleLogicalRange, fitContent } = fakeChart();
    expect(resetChartViewport(chart, '1Min', 900)).toBe(true);
    expect(applyOptions).toHaveBeenCalledWith({ autoScale: true });
    expect(setVisibleLogicalRange).toHaveBeenCalled();
    expect(fitContent).not.toHaveBeenCalled();
  });

  it('fits content for timeframes with no pinned window', () => {
    const { chart, fitContent } = fakeChart();
    expect(resetChartViewport(chart, '1Day', 40)).toBe(true);
    expect(fitContent).toHaveBeenCalled();
  });

  it('is a no-op without a chart and warns instead of throwing', () => {
    expect(resetChartViewport(null, '1Min', 100)).toBe(false);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const broken = {
      priceScale: () => {
        throw new Error('disposed');
      },
    } as unknown as IChartApi;
    expect(resetChartViewport(broken, '1Min', 100)).toBe(false);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
