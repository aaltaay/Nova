/** Levels the review panes draw. Computed with no bars after the as-of time. */

export interface ReviewLevels {
  hod: number | null;
  lod: number | null;
  premarket_high: number | null;
  opening_range_high: number | null;
  opening_range_low: number | null;
  prior_high: number | null;
  prior_low: number | null;
  prior_close: number | null;
}

export const REVIEW_LEVEL_COLORS = {
  high: '#ff8a70',
  low: '#45c7b8',
  prior: '#8aa4d6',
  setup: '#f59e0b',
} as const;

export interface ReviewPriceLine {
  title: string;
  price: number;
  color: string;
}

export function levelLines(levels: ReviewLevels): ReviewPriceLine[] {
  const rows: Array<[string, number | null, string]> = [
    ['HOD', levels.hod, REVIEW_LEVEL_COLORS.high],
    ['LOD', levels.lod, REVIEW_LEVEL_COLORS.low],
    ['PM high', levels.premarket_high, REVIEW_LEVEL_COLORS.high],
    ['OR high', levels.opening_range_high, REVIEW_LEVEL_COLORS.high],
    ['OR low', levels.opening_range_low, REVIEW_LEVEL_COLORS.low],
    ['Prior high', levels.prior_high, REVIEW_LEVEL_COLORS.prior],
    ['Prior low', levels.prior_low, REVIEW_LEVEL_COLORS.prior],
    ['Prior close', levels.prior_close, REVIEW_LEVEL_COLORS.prior],
  ];
  return rows.flatMap(([title, price, color]) => (price == null ? [] : [{ title, price, color }]));
}
