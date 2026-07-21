/** Sample scanner + catalyst rows — UI demo only; never mixed with live feeds. */
import type { Catalyst } from '../types/catalyst';
import type { Afterhours, Gapper, Mover } from '../types/scanner';
import type { NewsImpactVerdict } from '../types/newsImpact';

function impact(
  symbol: string,
  cls: NewsImpactVerdict['impact_class'],
  conf: number,
  headline: string,
): NewsImpactVerdict {
  return {
    symbol,
    impact_class: cls,
    confidence: conf,
    age_hours: 0.4,
    age_bucket: 'fresh',
    source_tier: 'tier1',
    source_name: 'Business Wire',
    confirmed_by_official: true,
    confirming_source_count: 2,
    price_reaction: cls === 'moved_price' ? 'up' : 'flat',
    attention: 'elevated',
    l2_reaction: 'unknown',
    sentiment: 'bullish',
    sentiment_score: 0.6,
    lexicon_sentiment: 'bullish',
    lexicon_polarity: 0.4,
    headline,
    headline_url: 'https://example.com/news',
    summary: `${symbol}: ${headline}`,
    reasons:
      cls === 'moved_price'
        ? ['price_reacted_up', 'high_confidence']
        : ['headline_attention', 'no_clear_price_move'],
    factors: {},
    ai_reasoning: null,
    rule_version: 'sample',
  };
}

function row(
  symbol: string,
  price: number,
  prev: number,
  volume: number,
  extras: Partial<Gapper> = {},
): Gapper {
  const change_abs = price - prev;
  const change_pct = prev > 0 ? (change_abs / prev) * 100 : 0;
  return {
    symbol,
    exchange: 'NASDAQ',
    price,
    prev_close: prev,
    change_pct,
    change_abs,
    gap_percent: change_pct,
    volume,
    rel_volume: extras.rel_volume ?? 8.2,
    has_news: extras.has_news ?? true,
    newest_headline_at: extras.newest_headline_at ?? '2026-07-19T12:05:00Z',
    market_cap: extras.market_cap ?? 45_000_000,
    float: extras.float ?? 12_000_000,
    short_interest: extras.short_interest ?? 2_500_000,
    short_ratio: extras.short_ratio ?? 1.2,
    ...extras,
  };
}

export const SAMPLE_GAPPERS: Gapper[] = [
  row('SMPL', 4.25, 2.8, 12_400_000, { rel_volume: 18.5, float: 4_200_000 }),
  row('GAPX', 1.92, 1.1, 28_000_000, { rel_volume: 42, float: 1_800_000 }),
  row('NWSR', 7.4, 5.9, 6_200_000, { rel_volume: 9.1 }),
  row('FLTX', 0.88, 0.52, 55_000_000, { rel_volume: 65, float: 900_000 }),
  row('CATZ', 12.3, 9.8, 3_100_000, { rel_volume: 5.4, market_cap: 180_000_000 }),
  row('MOMO', 3.15, 2.4, 19_500_000, { rel_volume: 22 }),
  row('RDYN', 5.6, 4.2, 8_800_000),
  row('BZAP', 2.05, 1.55, 14_200_000),
];

export const SAMPLE_GAINERS: Mover[] = [
  row('RUNR', 6.8, 4.1, 22_000_000, { gap_percent: null, rel_volume: 31 }),
  row('SPIK', 1.45, 0.95, 40_000_000, { gap_percent: null, rel_volume: 48 }),
  row('HODX', 9.2, 7.0, 11_000_000, { gap_percent: null }),
  row('VLTG', 3.9, 3.1, 9_400_000, { gap_percent: null }),
  row('PRNT', 15.6, 13.2, 4_200_000, { gap_percent: null, market_cap: 420_000_000 }),
  row('AQST', 2.7, 2.2, 16_000_000, { gap_percent: null }),
];

export const SAMPLE_LOSERS: Mover[] = [
  row('DRIP', 1.2, 1.85, 18_000_000, { gap_percent: null, rel_volume: 12 }),
  row('FADE', 4.1, 5.6, 7_500_000, { gap_percent: null }),
  row('SINK', 0.62, 0.95, 33_000_000, { gap_percent: null, float: 2_100_000 }),
  row('SLIP', 8.4, 10.1, 5_100_000, { gap_percent: null }),
  row('DUMP', 2.3, 3.0, 12_800_000, { gap_percent: null }),
];

export const SAMPLE_AFTERHOURS: Afterhours[] = [
  row('AHOT', 5.1, 4.4, 2_200_000, { gap_percent: 15.9, rel_volume: 3.2 }),
  row('NITE', 11.8, 10.9, 1_100_000, { gap_percent: 8.3 }),
  row('LATE', 0.77, 0.7, 4_800_000, { gap_percent: 10 }),
];

export const SAMPLE_CATALYSTS: Catalyst[] = [
  {
    symbol: 'SMPL',
    exchange: 'NASDAQ',
    previous_close: 2.8,
    current_price: 4.25,
    gap_percent: 51.8,
    volume: 12_400_000,
    has_news: true,
    newest_headline_at: '2026-07-19T11:58:00Z',
    catalyst_headline: 'SMPL wins FDA fast-track for rare disease drug',
    catalyst_url: 'https://example.com/smpl',
    catalyst_source: 'Business Wire',
    news_impact: impact('SMPL', 'moved_price', 0.86, 'SMPL wins FDA fast-track'),
  },
  {
    symbol: 'GAPX',
    exchange: 'NYSE',
    previous_close: 1.1,
    current_price: 1.92,
    gap_percent: 74.5,
    volume: 28_000_000,
    has_news: true,
    newest_headline_at: '2026-07-19T12:02:00Z',
    catalyst_headline: 'GAPX announces reverse merger LOI',
    catalyst_url: 'https://example.com/gapx',
    catalyst_source: 'GlobeNewswire',
    news_impact: impact('GAPX', 'moved_price', 0.78, 'GAPX reverse merger LOI'),
  },
  {
    symbol: 'NWSR',
    exchange: 'NASDAQ',
    previous_close: 5.9,
    current_price: 7.4,
    gap_percent: 25.4,
    volume: 6_200_000,
    has_news: true,
    newest_headline_at: '2026-07-19T10:40:00Z',
    catalyst_headline: 'NWSR mentioned on trading desk chatter',
    catalyst_url: 'https://example.com/nwsr',
    catalyst_source: 'Benzinga',
    news_impact: impact('NWSR', 'attention_only', 0.41, 'NWSR desk chatter'),
  },
  {
    symbol: 'CATZ',
    exchange: 'AMEX',
    previous_close: 9.8,
    current_price: 12.3,
    gap_percent: 25.5,
    volume: 3_100_000,
    has_news: true,
    newest_headline_at: '2026-07-19T09:15:00Z',
    catalyst_headline: 'CATZ earnings beat, raises guidance',
    catalyst_url: 'https://example.com/catz',
    catalyst_source: 'PR Newswire',
    news_impact: impact('CATZ', 'moved_price', 0.72, 'CATZ earnings beat'),
  },
  {
    symbol: 'MOMO',
    exchange: 'NASDAQ',
    previous_close: 2.4,
    current_price: 3.15,
    gap_percent: 31.3,
    volume: 19_500_000,
    has_news: true,
    newest_headline_at: '2026-07-19T12:10:00Z',
    catalyst_headline: 'MOMO short squeeze narrative spreads on social',
    catalyst_url: null,
    catalyst_source: 'Social',
    news_impact: impact('MOMO', 'attention_only', 0.35, 'MOMO social narrative'),
  },
];
