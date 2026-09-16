import { describe, expect, it } from 'vitest';
import { filterSignalNews, isJunkHeadline, newsChipFlameClass } from './newsJunk';

const BENZINGA_HEADLINE =
  "12 Health Care Stocks Moving In Tuesday's After-Market Session";
const BENZINGA_URL =
  'https://www.benzinga.com/trading-ideas/movers/26/09/61805393/12-health-care-stocks-moving-tuesday-s-after-market-session';

describe('isJunkHeadline', () => {
  it('flags the Benzinga movers example', () => {
    expect(isJunkHeadline(BENZINGA_HEADLINE, BENZINGA_URL)).toBe(true);
  });

  it('flags the same class of listicles', () => {
    expect(isJunkHeadline("5 Tech Stocks Moving In Friday's Pre-Market Session")).toBe(
      true,
    );
    expect(isJunkHeadline("Stocks To Watch: Tesla, Apple, Nvidia")).toBe(true);
    expect(isJunkHeadline('Top Premarket Movers For Wednesday')).toBe(true);
    expect(isJunkHeadline('Health Care Stocks To Watch This Week')).toBe(true);
  });

  it('keeps company-specific near-miss headlines', () => {
    expect(isJunkHeadline('AAPL surges after-hours on iPhone demand beat')).toBe(false);
    expect(isJunkHeadline('UNH stock moving higher after CMS rate decision')).toBe(
      false,
    );
    expect(isJunkHeadline('FDA approves PFE COVID booster')).toBe(false);
    expect(isJunkHeadline('JNJ to acquire Abiomed in $16.6 billion merger')).toBe(
      false,
    );
    expect(isJunkHeadline('Why NVDA is moving after hours')).toBe(false);
    expect(isJunkHeadline('Health care giant UNH reports Q2 earnings miss')).toBe(
      false,
    );
  });
});

describe('filterSignalNews + flame', () => {
  const now = Date.parse('2026-09-16T14:00:00Z');

  it('drops junk from the News column set', () => {
    const visible = filterSignalNews([
      {
        headline: BENZINGA_HEADLINE,
        url: BENZINGA_URL,
        created_at: '2026-09-16T13:50:00Z',
      },
      {
        headline: 'UNH reports Q2 earnings miss',
        url: 'https://www.reuters.com/unh-earnings',
        created_at: '2026-09-16T12:00:00Z',
      },
    ]);
    expect(visible.map((a) => a.headline)).toEqual(['UNH reports Q2 earnings miss']);
  });

  it('does not flame a junk headline even when it is fresh', () => {
    expect(
      newsChipFlameClass(
        {
          headline: BENZINGA_HEADLINE,
          url: BENZINGA_URL,
          created_at: '2026-09-16T13:30:00Z',
        },
        now,
      ),
    ).toBeNull();
  });

  it('flames a fresh company-specific headline', () => {
    expect(
      newsChipFlameClass(
        {
          headline: 'UNH reports Q2 earnings miss',
          url: 'https://www.reuters.com/unh-earnings',
          created_at: '2026-09-16T13:30:00Z',
        },
        now,
      ),
    ).toBe('flame-hot');
  });
});
