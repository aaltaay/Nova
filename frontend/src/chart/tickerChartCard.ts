/** Pure chrome math for TickerChart's card shell (kept out of the component). */
import {
  CHART_HEIGHT_GRID,
  CHART_HEIGHT_PAGE,
  CHART_HEIGHT_PANEL,
} from '../constants';

export type TickerChartVariant = 'panel' | 'page' | 'grid';

export function chartHeightForVariant(variant: TickerChartVariant): number {
  if (variant === 'grid') return CHART_HEIGHT_GRID;
  if (variant === 'page') return CHART_HEIGHT_PAGE;
  return CHART_HEIGHT_PANEL;
}

export function tickerChartCardClass(input: {
  variant: TickerChartVariant;
  maximized: boolean;
  compactChrome: boolean;
  focused: boolean;
}): string {
  return [
    'chart-card',
    input.maximized ? 'chart-card--maximized' : '',
    input.variant === 'grid' ? 'chart-card--grid' : '',
    input.compactChrome ? 'chart-card--compact' : '',
    input.focused ? 'chart-card--focused' : '',
  ]
    .filter(Boolean)
    .join(' ');
}
