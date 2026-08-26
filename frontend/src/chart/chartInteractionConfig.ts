/** Shared cursor behavior for chart inspection and drawing placement. */

import {
  CrosshairMode,
  type CrosshairOptions,
  type DeepPartial,
} from 'lightweight-charts';

export const CHART_CROSSHAIR_OPTIONS: DeepPartial<CrosshairOptions> = {
  mode: CrosshairMode.Normal,
  vertLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
  horzLine: { color: '#3b82f6', labelBackgroundColor: '#3b82f6' },
};
