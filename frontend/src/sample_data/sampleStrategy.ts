/** Sample watchlist rows for the isolated sample route -- the backend's shape
 * (strategy/watchlist.py): real pillar names, the row's market facts and
 * today's catalyst verdict (null where no source has looked). */
import type { WatchlistCatalyst, WatchlistEntry } from '../strategy/types';

const PILLARS = ['price', 'change_pct', 'relative_volume', 'catalyst', 'float'] as const;

function pillars(symbol: string, fails: readonly string[], details: Record<string, string>): WatchlistEntry['five_pillars'] {
  const checks = PILLARS.map(name => ({ name, passed: !fails.includes(name), detail: details[name] ?? '' }));
  const pass_count = checks.filter(c => c.passed).length;
  return {
    symbol,
    all_pass: pass_count === checks.length,
    pass_count,
    total: checks.length,
    checkmark: pass_count === checks.length ? '✓' : '',
    pillars: checks,
  };
}

function catalyst(category: string, title: string, minutesAgo: number): WatchlistCatalyst {
  return {
    verdict: 'catalyst', category, strength: 'strong', title, source: 'globenewswire',
    published_ts: Math.floor(Date.now() / 1000) - minutesAgo * 60, news_pending: false,
  };
}

export const SAMPLE_WATCHLIST: WatchlistEntry[] = [
  {
    symbol: 'SMPL', composite_score: 92,
    sub_scores: { change_pct: 95, relative_volume: 90, float: 88, catalyst: 94 },
    five_pillars: pillars('SMPL', [], { price: '$6.42', change_pct: '42.7% up', relative_volume: '18.2x', catalyst: 'FDA clearance', float: '3.1M' }),
    price: 6.42, change_pct: 0.427, rel_volume: 18.2, rvol_source: 'yfinance', float_shares: 3_100_000, has_news: true,
    catalyst: catalyst('fda_regulatory', 'Sample Corp receives FDA clearance', 48),
  },
  {
    symbol: 'GAPX', composite_score: 88,
    sub_scores: { change_pct: 98, relative_volume: 96, float: 92, catalyst: 80 },
    five_pillars: pillars('GAPX', [], { price: '$4.18', change_pct: '36.1% up', relative_volume: '11.4x', catalyst: 'contract', float: '6.8M' }),
    price: 4.18, change_pct: 0.361, rel_volume: 11.4, rvol_source: 'yfinance', float_shares: 6_800_000, has_news: true,
    catalyst: catalyst('contract_partnership', 'Gap X signs supply agreement', 95),
  },
  {
    symbol: 'MOMO', composite_score: 84,
    sub_scores: { change_pct: 85, relative_volume: 91, float: 86, catalyst: 0 },
    five_pillars: pillars('MOMO', ['catalyst'], { price: '$1.42', change_pct: '18.3% up', relative_volume: '9.7x', catalyst: 'no news', float: '4.2M' }),
    price: 1.42, change_pct: 0.183, rel_volume: 9.7, rvol_source: 'alpaca', float_shares: 4_200_000, has_news: false,
    catalyst: null,
  },
  {
    symbol: 'RUNR', composite_score: 79,
    sub_scores: { change_pct: 90, relative_volume: 82, float: 20, catalyst: 65 },
    five_pillars: pillars('RUNR', ['float'], { price: '$2.77', change_pct: '29.4% up', relative_volume: '7.9x', catalyst: '8-K', float: '14.5M' }),
    price: 2.77, change_pct: 0.294, rel_volume: 7.9, rvol_source: 'yfinance', float_shares: 14_500_000, has_news: true,
    catalyst: catalyst('merger_acquisition', 'Runner Inc. to be acquired', 130),
  },
  {
    symbol: 'NWSR', composite_score: 71,
    sub_scores: { change_pct: 72, relative_volume: 30, float: 75, catalyst: 55 },
    five_pillars: pillars('NWSR', ['relative_volume'], { price: '$3.05', change_pct: '19.6% up', relative_volume: '3.2x', catalyst: 'press release', float: '2.4M' }),
    price: 3.05, change_pct: 0.196, rel_volume: 3.2, rvol_source: 'yfinance', float_shares: 2_400_000, has_news: true,
    catalyst: { verdict: 'routine_only', category: 'corporate_routine', strength: null, title: 'NWSR to present at conference',
      source: 'prnewswire', published_ts: null, news_pending: false },
  },
];
