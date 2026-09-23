/** Sample watchlist rows for the isolated sample route. */
import type { WatchlistEntry } from '../strategy/types';

function pillars(symbol: string, pass: boolean): WatchlistEntry['five_pillars'] {
  const checks = [
    { name: 'Price', passed: true, detail: '$2–$20' },
    { name: 'Float', passed: true, detail: '<20M' },
    { name: 'RVOL', passed: pass, detail: pass ? '8x+' : '1.2x' },
    { name: 'Catalyst', passed: pass, detail: pass ? 'news' : 'weak' },
    { name: 'Trend', passed: true, detail: 'above VWAP' },
  ];
  const pass_count = checks.filter((c) => c.passed).length;
  return {
    symbol,
    all_pass: pass_count === checks.length,
    pass_count,
    total: checks.length,
    checkmark: pass_count === checks.length ? '✓' : `${pass_count}/5`,
    pillars: checks,
  };
}

export const SAMPLE_WATCHLIST: WatchlistEntry[] = [
  {
    symbol: 'SMPL',
    composite_score: 92,
    sub_scores: { change_pct: 95, relative_volume: 90, float: 88, catalyst: 94 },
    five_pillars: pillars('SMPL', true),
  },
  {
    symbol: 'GAPX',
    composite_score: 88,
    sub_scores: { change_pct: 98, relative_volume: 96, float: 92, catalyst: 80 },
    five_pillars: pillars('GAPX', true),
  },
  {
    symbol: 'MOMO',
    composite_score: 84,
    sub_scores: { change_pct: 85, relative_volume: 91, float: 86, catalyst: 70 },
    five_pillars: pillars('MOMO', true),
  },
  {
    symbol: 'NWSR',
    composite_score: 71,
    sub_scores: { change_pct: 72, relative_volume: 68, float: 75, catalyst: 55 },
    five_pillars: pillars('NWSR', false),
  },
  {
    symbol: 'RUNR',
    composite_score: 79,
    sub_scores: { change_pct: 90, relative_volume: 82, float: 70, catalyst: 65 },
    five_pillars: pillars('RUNR', true),
  },
];
