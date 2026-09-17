/**
 * Right price-scale gutter must stay a fixed width. Live last-value chips
 * (volume `9.0K` -> `149.04K`) used to auto-grow the axis and shove the plot.
 */
import type { DeepPartial, PriceScaleOptions } from 'lightweight-charts';

/** Reserved axis width -- must fit a padded volume chip plus price ticks. */
export const CHART_PRICE_SCALE_MIN_WIDTH_PX = 96;

/** Compact volume labels are padded to this budget so the chip cannot grow. */
export const CHART_VOLUME_LABEL_MAX_CHARS = 7;

const FIGURE_SPACE = '\u2007';

export function chartRightPriceScaleOptions(
  extra: DeepPartial<PriceScaleOptions> = {},
): DeepPartial<PriceScaleOptions> {
  return {
    borderColor: '#262a36',
    ...extra,
    minimumWidth: CHART_PRICE_SCALE_MIN_WIDTH_PX,
  };
}

export function formatChartVolumeLabel(value: number): string {
  if (!Number.isFinite(value)) {
    return FIGURE_SPACE.repeat(CHART_VOLUME_LABEL_MAX_CHARS);
  }
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  let body: string;
  if (abs >= 1e9) body = `${(abs / 1e9).toFixed(1)}B`;
  else if (abs >= 1e6) body = `${(abs / 1e6).toFixed(1)}M`;
  else if (abs >= 1e3) body = `${(abs / 1e3).toFixed(1)}K`;
  else body = abs.toFixed(1);
  const raw = `${sign}${body}`;
  if (raw.length >= CHART_VOLUME_LABEL_MAX_CHARS) {
    return raw.slice(0, CHART_VOLUME_LABEL_MAX_CHARS);
  }
  return raw.padStart(CHART_VOLUME_LABEL_MAX_CHARS, FIGURE_SPACE);
}
