import { describe, expect, it } from 'vitest';
import {
  CHART_PRICE_SCALE_MIN_WIDTH_PX,
  CHART_VOLUME_LABEL_MAX_CHARS,
  chartRightPriceScaleOptions,
  formatChartVolumeLabel,
} from './chartPriceScale';

describe('chartRightPriceScaleOptions', () => {
  it('pins a gutter wide enough that volume chips cannot shrink the plot', () => {
    const options = chartRightPriceScaleOptions({ borderColor: '#ff0000' });
    expect(options.minimumWidth).toBe(CHART_PRICE_SCALE_MIN_WIDTH_PX);
    expect(CHART_PRICE_SCALE_MIN_WIDTH_PX).toBeGreaterThanOrEqual(80);
    expect(options.borderColor).toBe('#ff0000');
  });

  it('does not let callers clear minimumWidth', () => {
    expect(chartRightPriceScaleOptions({ minimumWidth: 0 }).minimumWidth)
      .toBe(CHART_PRICE_SCALE_MIN_WIDTH_PX);
  });
});

describe('formatChartVolumeLabel', () => {
  it('keeps 9.0K and 149.04K the same character budget so the chip cannot grow', () => {
    const small = formatChartVolumeLabel(9_000);
    const large = formatChartVolumeLabel(149_040);
    expect(small.length).toBe(CHART_VOLUME_LABEL_MAX_CHARS);
    expect(large.length).toBe(CHART_VOLUME_LABEL_MAX_CHARS);
    expect(small).toContain('9.0K');
    expect(large).toContain('149.0K');
  });

  it('caps huge prints instead of emitting a wider string', () => {
    expect(formatChartVolumeLabel(12_345_678_900).length).toBe(CHART_VOLUME_LABEL_MAX_CHARS);
  });
});
