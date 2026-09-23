import { describe, expect, it } from 'vitest';
import { SAMPLE_HOD_ALERTS } from './sampleHod';
import {
  SAMPLE_AFTERHOURS,
  SAMPLE_CATALYSTS,
  SAMPLE_GAPPERS,
  SAMPLE_GAINERS,
  SAMPLE_LARGE_CAP,
  SAMPLE_LOSERS,
} from './sampleRows';
import { SAMPLE_WATCHLIST } from './sampleStrategy';

describe('sample fixtures populate every major surface', () => {
  it('has non-empty scanner / catalyst / HOD / watchlist sets', () => {
    expect(SAMPLE_GAPPERS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_GAINERS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_LOSERS.length).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_AFTERHOURS.length).toBeGreaterThanOrEqual(2);
    expect(SAMPLE_LARGE_CAP.length).toBeGreaterThanOrEqual(3);
    expect(SAMPLE_LARGE_CAP.some((r) => r.newest_headline_at != null)).toBe(true);
    expect(SAMPLE_LARGE_CAP.some((r) => r.earnings_day_offset != null)).toBe(true);
    expect(SAMPLE_CATALYSTS.length).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_HOD_ALERTS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_WATCHLIST.length).toBeGreaterThanOrEqual(4);
  });

  it('carries percent fields as fractions, like the live wire (QA W19: SMPL read "+5178.57%")', () => {
    const smpl = SAMPLE_GAPPERS.find((r) => r.symbol === 'SMPL')!;
    expect(smpl.change_pct).toBeCloseTo((4.25 - 2.8) / 2.8, 9);
    expect(smpl.gap_percent).toBeCloseTo(0.5179, 4);
    for (const row of [...SAMPLE_GAPPERS, ...SAMPLE_GAINERS, ...SAMPLE_LOSERS, ...SAMPLE_AFTERHOURS]) {
      expect(Math.abs(row.change_pct ?? 0)).toBeLessThan(5);
      expect(Math.abs(row.gap_percent ?? 0)).toBeLessThan(5);
    }
    for (const row of SAMPLE_LARGE_CAP) expect(Math.abs(row.change_5d_pct ?? 0)).toBeLessThan(1);
    for (const c of SAMPLE_CATALYSTS) expect(Math.abs(c.gap_percent)).toBeLessThan(5);
  });

  it('includes news_impact on catalysts', () => {
    expect(SAMPLE_CATALYSTS.every((c) => c.news_impact != null)).toBe(true);
  });
});
