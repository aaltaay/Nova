import { describe, expect, it } from 'vitest';
import { SAMPLE_HOD_ALERTS } from './sampleHod';
import {
  SAMPLE_AFTERHOURS,
  SAMPLE_CATALYSTS,
  SAMPLE_GAPPERS,
  SAMPLE_GAINERS,
  SAMPLE_LOSERS,
} from './sampleRows';
import { SAMPLE_DECISIONS, SAMPLE_WATCHLIST } from './sampleStrategy';

describe('sample fixtures populate every major surface', () => {
  it('has non-empty scanner / catalyst / HOD / watchlist / decide sets', () => {
    expect(SAMPLE_GAPPERS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_GAINERS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_LOSERS.length).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_AFTERHOURS.length).toBeGreaterThanOrEqual(2);
    expect(SAMPLE_CATALYSTS.length).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_HOD_ALERTS.length).toBeGreaterThanOrEqual(5);
    expect(SAMPLE_WATCHLIST.length).toBeGreaterThanOrEqual(4);
    expect(SAMPLE_DECISIONS.length).toBeGreaterThanOrEqual(3);
  });

  it('includes news_impact on catalysts and decide catalyst gates', () => {
    expect(SAMPLE_CATALYSTS.every((c) => c.news_impact != null)).toBe(true);
    const buy = SAMPLE_DECISIONS.find((d) => d.decision === 'BUY');
    const cat = buy?.gates.find((g) => g.name === 'catalyst');
    expect(cat?.evidence?.news_impact).toBeTruthy();
  });
});
