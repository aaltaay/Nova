/**
 * The scanner's sample morning at 09:41:27 ET (ADR 043): Nova Marketing Sample Data.
 * Sample tickers only; known real listings are left out on purpose.
 */
import { NOW_MS, NOW_S, iso } from './market';

const isoAgo = (min: number) => iso(NOW_MS - min * 60_000);

export interface Verdict {
  verdict: string;
  category: string;
  strength: string;
  title: string;
  source: string;
  published_ts: number;
  url: string;
  negative_too: boolean;
  rules_version: number;
  sources_answered: string[];
  n_items: number;
  news_pending: boolean;
  halt_code: string | null;
}

interface RowOptions {
  exchange?: string;
  gap_percent?: number | null;
  open?: number;
  rel_volume?: number;
  has_news?: boolean;
  newest_headline_at?: string | null;
  news_min?: number;
  market_cap?: number;
  float?: number;
  shares?: number;
  short_interest?: number;
  short_ratio?: number;
  halted?: boolean;
  catalyst?: Verdict;
  earnings_date?: string;
  earnings_session?: string;
  earnings_day_offset?: number;
}

function row(symbol: string, price: number, prev: number, volume: number, x: RowOptions = {}) {
  const change_abs = +(price - prev).toFixed(4);
  const change_pct = prev > 0 ? change_abs / prev : 0;
  const float = x.float ?? 12_000_000;
  const shares = x.shares ?? Math.round(float * 1.35);
  return {
    symbol,
    exchange: x.exchange ?? 'NASDAQ',
    price,
    prev_close: prev,
    change_pct,
    change_abs,
    gap_percent: x.gap_percent === undefined ? change_pct : x.gap_percent,
    open: x.open ?? null,
    volume,
    rel_volume: x.rel_volume ?? 8.2,
    rvol_source: 'yfinance',
    has_news: x.has_news ?? true,
    newest_headline_at: x.newest_headline_at === undefined ? isoAgo(x.news_min ?? 160) : x.newest_headline_at,
    market_cap: x.market_cap ?? Math.round(price * (x.shares ?? float * 1.4)),
    float,
    shares_outstanding: shares,
    float_contradicted: false,
    float_contradicted_reason: null,
    short_interest: x.short_interest ?? 1_200_000,
    short_interest_ts: Date.UTC(2026, 8, 15) / 1000,
    short_ratio: x.short_ratio ?? 1.4,
    short_above_float: false,
    short_above_float_reason: null,
    halted: x.halted ?? false,
    quote_quality: null,
    large_cap_score: null,
    catalyst: x.catalyst ?? null,
    earnings_date: x.earnings_date ?? null,
    earnings_session: x.earnings_session ?? null,
    earnings_day_offset: x.earnings_day_offset ?? null,
  };
}

export type ScannerRow = ReturnType<typeof row>;

function verdict(kind: string, category: string, strength: string, title: string, source: string, minAgo: number): Verdict {
  return {
    verdict: kind,
    category,
    strength,
    title,
    source,
    published_ts: NOW_S - minAgo * 60,
    url: 'https://example.com/nova-sample-news',
    negative_too: false,
    rules_version: 7,
    sources_answered: ['alpaca', 'finnhub', 'globenewswire', 'edgar'],
    n_items: 3,
    news_pending: false,
    halt_code: null,
  };
}

export const GAPPERS: ScannerRow[] = [
  row('SMPL', 4.33, 2.8, 31_240_000, {
    rel_volume: 24.8, float: 4_200_000, short_interest: 610_000, short_ratio: 0.9, open: 4.18, news_min: 161,
    catalyst: verdict('catalyst', 'fda_regulatory', 'strong', 'Sample Pharma receives FDA Fast Track designation for SMP-201', 'GlobeNewswire', 161),
  }),
  row('GAPX', 1.92, 1.1, 28_060_000, {
    rel_volume: 42.3, float: 1_800_000, short_interest: 240_000, open: 1.71, news_min: 214,
    catalyst: verdict('catalyst', 'merger_acquisition', 'strong', 'GapX Holdings signs merger agreement with private AI infrastructure firm', 'PR Newswire', 214),
  }),
  row('FLTX', 0.88, 0.52, 55_310_000, {
    rel_volume: 65.1, float: 900_000, short_interest: 95_000, open: 0.79, news_min: 95,
    catalyst: verdict('catalyst', 'contract_partnership', 'strong', 'Floatix wins $40M multi-year supply contract', 'Business Wire', 95),
  }),
  row('RDYN', 5.6, 4.2, 8_840_000, {
    rel_volume: 11.6, float: 6_400_000, open: 5.31, news_min: 300,
    catalyst: verdict('catalyst', 'earnings', 'weak', 'Rydin Therapeutics reports Q3 revenue up 82%', 'GlobeNewswire', 300),
  }),
  row('BZAP', 2.05, 1.55, 14_220_000, { rel_volume: 18.9, float: 3_900_000, open: 1.94, has_news: false, newest_headline_at: null }),
  row('MMTX', 3.15, 2.4, 19_520_000, {
    rel_volume: 22.4, float: 7_700_000, open: 2.98, news_min: 70,
    catalyst: verdict('catalyst', 'clinical_data', 'strong', 'Momentix announces positive Phase 2 topline data', 'Business Wire', 70),
  }),
  row('NWSR', 7.4, 5.9, 6_210_000, {
    rel_volume: 9.1, float: 11_000_000, open: 7.05, news_min: 410,
    catalyst: verdict('routine_only', 'company_news', 'weak', 'NewsWire Co. to present at investor conference', 'Accesswire', 410),
  }),
  row('CATZ', 12.3, 9.8, 3_120_000, {
    exchange: 'NYSE', rel_volume: 5.4, float: 18_000_000, open: 11.82, news_min: 520,
    earnings_date: '2026-09-30', earnings_session: 'bmo', earnings_day_offset: 0,
    catalyst: verdict('catalyst', 'earnings', 'strong', 'Catz Brands beats estimates and raises full-year guidance', 'PR Newswire', 520),
  }),
  row('VYTL', 1.37, 1.12, 9_800_000, { rel_volume: 7.3, float: 5_100_000, open: 1.31, has_news: false, newest_headline_at: null }),
  row('ORBQ', 3.62, 2.95, 4_410_000, { rel_volume: 6.1, float: 9_600_000, open: 3.44, news_min: 600 }),
  row('HELQ', 9.84, 8.31, 2_050_000, { exchange: 'NYSE', rel_volume: 4.2, float: 22_000_000, open: 9.55, news_min: 1200 }),
  row('KRYQ', 6.18, 5.2, 1_920_000, { rel_volume: 3.8, float: 15_000_000, open: 6.01, has_news: false, newest_headline_at: null }),
];

export const GAINERS: ScannerRow[] = [
  row('RUNR', 6.8, 4.1, 22_030_000, {
    gap_percent: null, rel_volume: 31.2, float: 3_300_000, news_min: 55,
    catalyst: verdict('catalyst', 'contract_partnership', 'strong', 'Runner Dynamics expands defense program award', 'GlobeNewswire', 55),
  }),
  ...GAPPERS.slice(0, 3).map((r) => ({ ...r, gap_percent: null })),
  row('SPIK', 1.45, 0.95, 40_120_000, { gap_percent: null, rel_volume: 48.7, float: 1_200_000, news_min: 38 }),
  row('HODX', 9.2, 7.0, 11_040_000, { gap_percent: null, rel_volume: 14.3, float: 8_000_000, news_min: 126 }),
  row('VLTG', 3.9, 3.1, 9_420_000, { gap_percent: null, rel_volume: 10.2, float: 6_600_000, has_news: false, newest_headline_at: null }),
];

export const LOSERS: ScannerRow[] = [
  row('DRIP', 1.2, 1.85, 18_000_000, {
    gap_percent: null, rel_volume: 12.4,
    catalyst: verdict('negative', 'dilution', 'strong', 'Drip Corp prices $12M registered direct offering', 'GlobeNewswire', 180),
  }),
  row('FADE', 4.1, 5.6, 7_500_000, { gap_percent: null }),
  row('SINK', 0.62, 0.95, 33_000_000, { gap_percent: null, float: 2_100_000 }),
  row('SLIP', 8.4, 10.1, 5_100_000, { gap_percent: null }),
];

/** Every sample row by symbol (gappers win over the gainers' copies). */
export const ROWS: ReadonlyMap<string, ScannerRow> = new Map(
  [...LOSERS, ...GAINERS, ...GAPPERS].map((r) => [r.symbol, r] as const),
);

export const CATALYSTS = GAPPERS.filter((r) => r.catalyst?.verdict === 'catalyst').map((r) => ({
  symbol: r.symbol,
  exchange: r.exchange,
  previous_close: r.prev_close,
  current_price: r.price,
  gap_percent: r.change_pct,
  volume: r.volume,
  has_news: true,
  newest_headline_at: r.newest_headline_at,
  catalyst_headline: r.catalyst?.title ?? null,
  catalyst_url: r.catalyst?.url ?? null,
  catalyst_source: r.catalyst?.source ?? null,
  news_impact: null,
}));

interface AlertOptions {
  rvol?: number;
  rvol_5min?: number;
  float?: number;
  gap?: number;
  volume?: number;
  mom?: number;
  count?: number;
  span?: number;
  strategies?: { id: number; name: string }[];
}

function alert(ticker: string, sid: number, sname: string, price: number, chg: number, minAgo: number, x: AlertOptions = {}) {
  const ms = NOW_MS - minAgo * 60_000;
  const id = `${ms}-${ticker}-${sid}`;
  return {
    id,
    timestamp: iso(ms),
    ticker,
    strategy_id: sid,
    strategy_name: sname,
    price,
    change_pct: chg,
    rvol: x.rvol ?? 12.5,
    rvol_5min: x.rvol_5min ?? 8.2,
    float_shares: x.float ?? 4_200_000,
    gap_pct: x.gap ?? 28,
    volume: x.volume ?? 9_500_000,
    momentum_pct: x.mom ?? 6.4,
    rvol_source: 'yfinance',
    consolidation_count: x.count ?? 1,
    consolidated_ids: [id],
    consolidation_span_sec: x.span ?? null,
    created_ts: ms / 1000,
    strategies: x.strategies,
    has_news: true,
  };
}

/** HOD Momo alerts, newest first (generic strategy names). */
export const HOD_ALERTS = [
  alert('SMPL', 13, 'HOD Break', 4.33, 54.6, 0.2, {
    rvol: 24.8, rvol_5min: 9.6, float: 4_200_000, gap: 2.1, volume: 31_240_000, mom: 4.1, count: 3, span: 4,
    strategies: [{ id: 13, name: 'HOD Break' }, { id: 3, name: '5min Surge' }],
  }),
  alert('SPIK', 3, '5min Surge', 1.45, 52.6, 1.4, { rvol: 48.7, float: 1_200_000, gap: 0, volume: 40_120_000, mom: 9.1 }),
  alert('RUNR', 13, 'HOD Break', 6.8, 65.9, 2.6, { rvol: 31.2, float: 3_300_000, volume: 22_030_000, mom: 7.3 }),
  alert('GAPX', 4, 'Low Float Runner', 1.92, 74.5, 4.1, { rvol: 42.3, float: 1_800_000, gap: 55.5, volume: 28_060_000, mom: 5.2 }),
  alert('FLTX', 4, 'Low Float Runner', 0.88, 69.2, 6.8, { rvol: 65.1, float: 900_000, gap: 51.9, volume: 55_310_000, mom: 6.0 }),
  alert('MMTX', 2, 'Premarket HOD', 3.15, 31.3, 11.5, { rvol: 22.4, float: 7_700_000, gap: 24.2, volume: 19_520_000, mom: 3.4 }),
  alert('HODX', 3, '5min Surge', 9.2, 31.4, 15.2, { rvol: 14.3, float: 8_000_000, volume: 11_040_000, mom: 4.8 }),
  alert('RDYN', 13, 'HOD Break', 5.6, 33.3, 19.7, { rvol: 11.6, float: 6_400_000, gap: 26.4, volume: 8_840_000, mom: 3.9 }),
  alert('SMPL', 2, 'Premarket HOD', 4.12, 47.1, 23.3, { rvol: 21.2, float: 4_200_000, gap: 2.1, volume: 18_400_000, mom: 3.0 }),
  alert('VLTG', 5, 'Parabolic', 3.9, 25.8, 31.0, { rvol: 10.2, float: 6_600_000, volume: 9_420_000, mom: 11.2 }),
];

const STRATEGY_COLORS: ReadonlyArray<readonly [number, string, string]> = [
  [13, 'HOD Break', '#22c55e'], [2, 'Premarket HOD', '#3b82f6'], [3, '5min Surge', '#f59e0b'],
  [4, 'Low Float Runner', '#a855f7'], [5, 'Parabolic', '#ef4444'],
];

export const HOD_CONFIG = {
  master: {
    hod_required: true, surge_pct: 3, surge_window_min: 5, min_volume: 100_000, min_price: 1, min_rvol: 1.5,
    premarket_min_rvol: 1, afterhours_min_rvol: 1, cooldown_sec: 60, consolidation_sec: 5,
  },
  strategies: Object.fromEntries(STRATEGY_COLORS.map(([id, name, color]) => [String(id), {
    strategy_id: id, name, color, enabled: true, audio: false, notes: 'Nova Marketing Sample Data',
    min_price: 0.5, max_price: 20, min_float: 0, max_float: 20_000_000, min_volume: 100_000, min_rvol: 2, max_rvol: 1000,
    min_gap_pct: 0, max_gap_pct: 500, min_change_pct: 0, max_change_pct: 500, surge_pct: 3, surge_window_min: 5,
    surge_method: 'low_to_current', proximity_52wk_pct: 0, former_momo_list: [], requires_hod: true,
  }])),
};

const PILLARS = ['price', 'change_pct', 'relative_volume', 'catalyst', 'float'] as const;

function pillarSet(r: ScannerRow) {
  const passes: Record<(typeof PILLARS)[number], boolean> = {
    price: r.price >= 1 && r.price <= 20,
    change_pct: r.change_pct >= 0.1,
    relative_volume: r.rel_volume >= 5,
    catalyst: r.catalyst?.verdict === 'catalyst',
    float: r.float <= 10_000_000,
  };
  const detail: Record<(typeof PILLARS)[number], string> = {
    price: `$${r.price.toFixed(2)}`,
    change_pct: `${(r.change_pct * 100).toFixed(1)}% up`,
    relative_volume: `${r.rel_volume.toFixed(1)}x`,
    catalyst: r.catalyst ? r.catalyst.category.replace(/_/g, ' ') : 'no news',
    float: `${(r.float / 1e6).toFixed(1)}M`,
  };
  const checks = PILLARS.map((name) => ({ name, passed: passes[name], detail: detail[name] }));
  const pass_count = checks.filter((c) => c.passed).length;
  return { symbol: r.symbol, all_pass: pass_count === 5, pass_count, total: 5, checkmark: pass_count === 5 ? '✓' : '', pillars: checks };
}

export const WATCHLIST = GAPPERS.map((r) => {
  const fp = pillarSet(r);
  return {
    symbol: r.symbol,
    composite_score: Math.round(40 + fp.pass_count * 9 + Math.min(10, r.rel_volume / 5)),
    sub_scores: {
      change_pct: Math.min(100, Math.round(r.change_pct * 140)),
      relative_volume: Math.min(100, Math.round(r.rel_volume * 2.2)),
      float: r.float <= 10e6 ? 90 : 35,
      catalyst: r.catalyst?.verdict === 'catalyst' ? 92 : 10,
    },
    five_pillars: fp,
    price: r.price,
    change_pct: r.change_pct,
    rel_volume: r.rel_volume,
    rvol_source: 'yfinance',
    float_shares: r.float,
    has_news: r.has_news,
    catalyst: r.catalyst ? {
      verdict: r.catalyst.verdict, category: r.catalyst.category, strength: r.catalyst.strength,
      title: r.catalyst.title, source: r.catalyst.source, published_ts: r.catalyst.published_ts, news_pending: false,
    } : null,
  };
}).sort((a, b) => b.composite_score - a.composite_score);
