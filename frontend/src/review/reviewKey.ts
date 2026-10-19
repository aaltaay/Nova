/** Key chip rows for a review pane. Colours match the lines the pane draws. */

import {
  CHART_EMA_COLORS,
  CHART_EMA_LENGTHS,
  CHART_SESSION_COLORS,
  CHART_VWAP_COLOR,
  type ChartIndicatorId,
} from '../constants';
import type { KeySection } from '../stock_read';
import { REVIEW_LEVEL_COLORS, type ReviewLevels } from './reviewLevels';
import type { ReviewTf } from './reviewQuery';

export function reviewKey(tf: ReviewTf, enabled: ChartIndicatorId[], levels: ReviewLevels, setupCount: number): KeySection[] {
  const sections: KeySection[] = [];
  if (tf !== '1d') {
    sections.push({
      title: 'Session',
      rows: [
        { swatch: 'band', color: CHART_SESSION_COLORS.premarket, label: 'Premarket', text: 'Before 09:30 ET' },
        { swatch: 'band', color: CHART_SESSION_COLORS.rth, label: 'Regular', text: '09:30 to 16:00 ET' },
      ],
    });
  }
  const levelRows = [
    levels.hod != null ? { swatch: 'line' as const, color: REVIEW_LEVEL_COLORS.high, label: 'HOD', text: 'High since 04:00' } : null,
    levels.lod != null ? { swatch: 'line' as const, color: REVIEW_LEVEL_COLORS.low, label: 'LOD', text: 'Low since 04:00' } : null,
    levels.premarket_high != null ? { swatch: 'dash' as const, color: REVIEW_LEVEL_COLORS.high, label: 'PM high', text: 'High before the open' } : null,
    levels.opening_range_high != null ? { swatch: 'dash' as const, color: REVIEW_LEVEL_COLORS.high, label: 'OR high', text: '09:30 to 09:35 high' } : null,
    levels.opening_range_low != null ? { swatch: 'dash' as const, color: REVIEW_LEVEL_COLORS.low, label: 'OR low', text: '09:30 to 09:35 low' } : null,
    levels.prior_close != null ? { swatch: 'dots' as const, color: REVIEW_LEVEL_COLORS.prior, label: 'Prior close', text: 'Yesterday close' } : null,
  ].filter((row) => row !== null);
  if (levelRows.length) sections.push({ title: 'Levels', rows: levelRows });
  const overlays = [];
  if (enabled.includes('emas')) {
    for (const length of CHART_EMA_LENGTHS) {
      overlays.push({ swatch: 'line' as const, color: CHART_EMA_COLORS[length], label: `${length} EMA`, text: 'Closes only, no future bar' });
    }
  }
  if (enabled.includes('vwap') && tf !== '1d') {
    overlays.push({ swatch: 'dash' as const, color: CHART_VWAP_COLOR, label: 'VWAP', text: 'Anchored at 04:00 ET' });
  }
  if (overlays.length) sections.push({ title: 'Indicators', rows: overlays });
  if (setupCount > 0) {
    sections.push({
      title: 'Setups',
      rows: [{ swatch: 'line', color: REVIEW_LEVEL_COLORS.setup, label: 'Flat top', text: 'Three closed 5-minute highs' }],
    });
  }
  return sections;
}
