/**
 * Nova Marketing Sample Data for the Market page (ADR 053): the approved mockup's figures (Monday 2026-10-12,
 * 09:52 ET), shown on the sample desk and the demo build. Nothing here is read live.
 */
import type { BlockPeriods, BoardRow, Climate, MarketBoard, Period, QuoteTile, TopCard } from './types';

const NOW = Date.UTC(2026, 9, 12, 13, 52, 14) / 1000;
const DAY_0400 = Date.UTC(2026, 9, 12, 8, 0, 0) / 1000;

function seeded(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A path from `start` to `end` over `n` points (a random walk pinned at both ends). */
function walk(seed: number, n: number, start: number, end: number, vol: number): number[] {
  const r = seeded(seed);
  const raw = [0];
  for (let i = 1; i < n; i += 1) raw.push(raw[i - 1] + (r() - 0.5) * vol);
  const last = raw[n - 1];
  return raw.map((x, i) => start + (x - (last * i) / (n - 1)) + ((end - start) * i) / (n - 1));
}

function tile(
  id: string, label: string, symbol: string, kind: QuoteTile['kind'], exchange: string, contract: string | null,
  last: number, prev: number, seed: number,
): QuoteTile {
  const pts = walk(seed, 72, prev + (last - prev) * 0.5, last, Math.abs(last - prev) * 0.25 + prev * 0.0004);
  return {
    id, label, symbol, kind, exchange, contract, last, prev_close: prev, change: last - prev,
    change_pct: Math.round(10000 * (last / prev - 1)) / 100, price_basis: 'last', data_type: 'live', at: NOW, stale: false,
    line: pts.map((v, i) => [DAY_0400 + i * 300, v] as [number, number]), error: null,
  };
}

const SECTORS: [string, string, number, number, string | null, number][] = [
  ['Technology', 'XLK', 1.48, 1.37, 'NVDA', 3.4], ['Communication', 'XLC', 1.12, 1.75, 'META', 2.6],
  ['Consumer disc.', 'XLY', 0.94, 2.69, 'TSLA', 4.1], ['Industrials', 'XLI', 0.61, 0.32, 'GE', 2.2],
  ['Financials', 'XLF', 0.44, 1.32, 'COIN', 3.9], ['Materials', 'XLB', 0.21, 1.16, 'FCX', 1.9],
  ['Health care', 'XLV', 0.08, -0.96, 'LLY', 1.7], ['Real estate', 'XLRE', -0.18, -0.82, null, 0],
  ['Staples', 'XLP', -0.36, -0.25, 'WMT', 0.6], ['Utilities', 'XLU', -0.52, -2.43, 'VST', 1.2],
  ['Energy', 'XLE', -1.38, -2.65, null, 0],
];

const INDUSTRIES: [string, string, number, number, string | null, number, boolean][] = [
  ['Biotech', 'XBI', 1.92, 6.84, 'SRPT', 7.2, true], ['Crypto stocks', 'WGMI', 1.85, 5.92, null, 0, false],
  ['Quantum', 'QTUM', 1.66, 4.71, null, 0, false], ['Nuclear & uranium', 'URA', 0.88, 3.88, null, 0, false],
  ['Semiconductors', 'SMH', 2.36, 3.15, null, 0, false], ['AI & robotics', 'BOTZ', 1.04, 2.4, null, 0, false],
  ['Software', 'IGV', 1.21, 1.84, null, 0, false], ['China internet', 'KWEB', 0.71, 1.62, null, 0, false],
  ['Airlines', 'JETS', 1.1, 1.05, null, 0, false], ['Regional banks', 'KRE', 0.38, 0.42, 'WAL', 2.0, true],
  ['Gold miners', 'GDX', -0.24, -0.38, null, 0, false], ['Homebuilders', 'XHB', -0.12, -0.95, 'TOL', 1.1, true],
  ['Solar', 'TAN', -0.65, -1.86, null, 0, false], ['Cannabis', 'MSOS', -1.2, -3.4, null, 0, false],
  ['Oil & gas producers', 'XOP', -2.05, -4.12, null, 0, true],
];

function boardRows(period: Period, industries: boolean): BoardRow[] {
  const rows = industries
    ? INDUSTRIES.map(([name, etf, d1, d7, ld, lp, file]) => ({ name, etf, d1, d7, ld, lp, file }))
    : SECTORS.map(([name, etf, d1, d7, ld, lp]) => ({ name, etf, d1, d7, ld, lp, file: true }));
  const out = rows.map((r) => {
    const main = period === '1D' ? r.d1 : period === '7D' ? r.d7 : Math.round(r.d7 * 2.6 * 100) / 100;
    return {
      name: r.name, etf: r.etf, change_pct: main, context_pct: period === '1D' ? r.d7 : r.d1,
      context_period: (period === '1D' ? '7D' : '1D') as Period,
      leader: r.ld && period === '1D' ? { symbol: r.ld, change_pct: r.lp } : null,
      leader_why: !r.file ? 'no member list for this ETF' : r.ld && period === '1D' ? null : 'none in the movers',
    };
  });
  return out.sort((a, b) => b.change_pct - a.change_pct);
}

const TOP: [string, string, number, [string, number, number][]][] = [
  ['Technology', 'XLK', 1.48, [['AMD', 241.12, 4.8], ['NVDA', 198.4, 3.4], ['PLTR', 184.55, 3.0], ['AVGO', 352.8, 2.7], ['MU', 162.35, 2.5]]],
  ['Communication', 'XLC', 1.12, [['RDDT', 231.6, 5.2], ['META', 742.1, 2.6], ['NFLX', 1212.4, 1.9], ['GOOGL', 248.75, 1.4], ['TTWO', 251.2, 1.2]]],
  ['Consumer disc.', 'XLY', 0.94, [['TSLA', 438.2, 4.1], ['RIVN', 14.62, 3.6], ['CVNA', 362.1, 2.9], ['AMZN', 231.45, 1.2], ['NKE', 71.8, 1.0]]],
  ['Industrials', 'XLI', 0.61, [['GE', 301.2, 2.2], ['UBER', 98.4, 1.8], ['CAT', 512.3, 1.1], ['RTX', 158.9, 0.7], ['HON', 214.6, 0.4]]],
  ['Financials', 'XLF', 0.44, [['COIN', 352.15, 3.9], ['HOOD', 138.7, 3.8], ['SCHW', 96.4, 1.6], ['JPM', 309.25, 1.3], ['GS', 791.6, 1.1]]],
  ['Materials', 'XLB', 0.21, [['FCX', 48.2, 1.9], ['NEM', 92.4, 1.2], ['LIN', 468.1, 0.4], ['SHW', 341.7, 0.1], ['APD', 288.3, -0.3]]],
  ['Health care', 'XLV', 0.08, [['LLY', 812.5, 1.7], ['ISRG', 548.2, 0.9], ['ABBV', 221.4, 0.2], ['JNJ', 189.6, -0.4], ['UNH', 352.8, -1.2]]],
  ['Real estate', 'XLRE', -0.18, [['WELL', 171.3, 0.6], ['PLD', 118.9, 0.1], ['AMT', 196.2, -0.3], ['EQIX', 812.4, -0.5], ['SPG', 178.5, -0.9]]],
  ['Staples', 'XLP', -0.36, [['WMT', 101.8, 0.6], ['COST', 921.4, 0.2], ['PG', 152.3, -0.4], ['KO', 68.9, -0.7], ['PEP', 141.2, -1.1]]],
  ['Utilities', 'XLU', -0.52, [['VST', 196.7, 1.2], ['CEG', 344.1, 0.8], ['NEE', 81.2, -0.6], ['SO', 92.5, -0.9], ['DUK', 121.4, -1.3]]],
  ['Energy', 'XLE', -1.38, [['KMI', 27.45, 0.4], ['WMB', 58.1, 0.1], ['XOM', 112.3, -1.1], ['CVX', 154.85, -1.5], ['OXY', 42.15, -2.8]]],
];

function topCards(kind: BlockPeriods['top']['kind'], period: Period): TopCard[] {
  if (kind === 'runners') {
    return [
      { name: 'Biotechnology', etf: null, change_pct: null, rows: [
        { symbol: 'RUNR', last: 4.86, change_pct: 212, spark: null }, { symbol: 'NVXA', last: 2.11, change_pct: 184, spark: null },
        { symbol: 'CATZ', last: 1.42, change_pct: 61, spark: null }] },
      { name: 'Software', etf: null, change_pct: null, rows: [{ symbol: 'QMBL', last: 6.3, change_pct: 141, spark: null }] },
      { name: 'Diversified Finan Serv', etf: null, change_pct: null, rows: [{ symbol: 'KSTR', last: 3.9, change_pct: 88, spark: null }] },
    ];
  }
  return TOP.map(([name, etf, pct, rows], k) => ({
    name, etf, change_pct: pct,
    rows: rows.map(([symbol, last, chg], j) => ({
      symbol, last, change_pct: period === '1D' ? chg : Math.round(chg * (period === '7D' ? 2.2 : 4.1) * 10) / 10,
      spark: period === '1D' ? null : walk(300 + k * 13 + j, period === '7D' ? 6 : 22, last / (1 + chg / 50), last, last * 0.02),
    })),
  }));
}

function climateDays(): Climate['days'] {
  const totals = [9, 11, 8, 10, 12, 7, 9, 10, 13, 11, 8, 9, 10, 12, 9, 11, 12, 15, 14, 10, 17];
  const dates = ['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-21', '2026-09-22',
    '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02',
    '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-12'];
  return totals.map((total, i): Climate['days'][number] => {
    if (i === 3 || i === 4) return { date: dates[i], source: null, total: null, themes: {} };   // not recorded
    const bio = Math.round(total * (0.15 + 0.3 * (i / 20)));
    const crypto = Math.round(total * (0.35 - 0.2 * (i / 20)));
    const soft = Math.round(total * 0.15);
    return { date: dates[i], source: 'recorded', total,
      themes: { Biotechnology: bio, 'Diversified Finan Serv': crypto, Software: soft, Pharmaceuticals: Math.max(0, total - bio - crypto - soft) } };
  });
}

export function sampleMarketBoard(p: BlockPeriods): MarketBoard {
  const es = tile('es', 'S&P 500 futures', 'ES', 'future', 'CME', 'ESZ6', 6842.5, 6800.25, 11);
  const rty = tile('rty', 'Russell 2000 futures', 'RTY', 'future', 'CME', 'RTYZ6', 2486.3, 2454.2, 25);
  const quotes: QuoteTile[] = [
    es,
    tile('nq', 'Nasdaq 100 futures', 'NQ', 'future', 'CME', 'NQZ6', 25310.75, 25075.25, 18),
    rty,
    tile('ym', 'Dow futures', 'YM', 'future', 'CBOT', 'YMZ6', 47215, 47084, 32),
    tile('vix', 'VIX fear gauge', 'VIX', 'index', 'CBOE', null, 15.84, 16.89, 39),
    { ...tile('tnx', '10-year yield', 'TNX', 'index', 'CBOE', null, 4.12, 4.12, 46), line: [], change: 0, change_pct: 0 },
    tile('cl', 'Crude oil futures', 'CL', 'future', 'NYMEX', 'CLX6', 61.85, 63.27, 60),
    tile('gc', 'Gold futures', 'GC', 'future', 'COMEX', 'GCZ6', 4112.4, 4104.1, 67),
    tile('btc', 'Bitcoin', 'BTC', 'crypto', 'ZEROHASH', null, 118420, 115984, 74),
    { ...tile('small_caps', 'Small caps vs S&P', 'RTY - ES', 'spread', '', null, 0.69, 0.0001, 81),
      last: null, prev_close: null, change: null, change_pct: 0.69 },
  ];
  const climatePeriod = p.climate;
  const n = climatePeriod === '1D' ? 1 : climatePeriod === '7D' ? 5 : 21;
  const days = climateDays();
  const inPeriod = days.slice(-n);
  const total = inPeriod.reduce((a, d) => a + (d.total ?? 0), 0);
  const themes: Record<string, number> = {};
  inPeriod.forEach((d) => Object.entries(d.themes).forEach(([k, v]) => { themes[k] = (themes[k] ?? 0) + v; }));
  const names = Object.keys(themes).sort((a, b) => themes[b] - themes[a]);
  return {
    schema_version: 1, generated_at: NOW, enabled: true, loading: false, replay_desk: false,
    session: { date: '2026-10-12', phase: 'regular', open_at: NOW - 22 * 60 - 14, close_at: NOW + 6 * 3600 + 7 * 60 + 46,
      next: { kind: 'close', at: NOW + 6 * 3600 + 7 * 60 + 46 }, holiday: null },
    day_read: { verdict: 'bullish', green: 5, red: 0, known: 6, total: 6, checks: [
      { id: 'futures', label: 'Futures up across the board', state: 'green', value: 4, text: '4 of 4 up', starts_at: null, why: null },
      { id: 'breadth', label: 'Breadth: advancers vs decliners', state: 'green', value: 2.4, text: '2.4 : 1', starts_at: null, why: null },
      { id: 'vix', label: 'Fear gauge falling (VIX)', state: 'green', value: -6.22, text: '15.84', starts_at: null, why: null },
      { id: 'small_caps', label: 'Small caps beating large caps', state: 'green', value: 0.69, text: '+0.69 pt', starts_at: null, why: null },
      { id: 'runners', label: 'Small-cap runners above normal', state: 'green', value: 17, text: '17 vs 11 avg', starts_at: null, why: null },
      { id: 'gappers', label: 'Gappers holding their open', state: 'amber', value: 58.3, text: '7 of 12', starts_at: null, why: null },
    ] },
    events: { items: [
      { at: NOW + 8 * 60, kind: 'econ', title: 'CPI', detail: 'Consumer Price Index for September', source: 'bls' },
      { at: NOW + 4 * 3600 + 7 * 60 + 46, kind: 'fomc', title: 'FOMC decision', detail: 'Fed statement and rate', source: 'fed' },
    ], bond_market: { closed: true, early_close_at: null, why: 'Columbus Day' } },
    quotes,
    breadth: { state: 'ok', why: null, at: NOW, data_type: 'live', advancing: 2012, declining: 838, unchanged: 96,
      up_volume: 780, down_volume: 220, tick: 412, trin: 0.74,
      ad_line: walk(77, 22, 120, 1174, 260).map((v, i) => [NOW - (21 - i) * 60, v] as [number, number]),
      line_since: NOW - 22 * 60, prior: null },
    sectors: { period: p.sectors, from: '2026-10-12', to: '2026-10-12', rows: boardRows(p.sectors, false),
      offense_pct: 1.18, defense_pct: -0.27 },
    industries: { period: p.industries, from: '2026-10-06', to: '2026-10-12', rows: boardRows(p.industries, true) },
    climate: {
      period: climatePeriod, from: inPeriod[0].date, to: '2026-10-12', sessions: n, covered: inPeriod.filter((d) => d.source).length,
      lens: { board: 'gainers', rank_max: 50, price_min: 0.5 },
      counts: { up20: total, up50: Math.round(total * 0.33), up100: Math.round(total * 0.11) },
      per_day: Math.round((10 * total) / n) / 10,
      baseline: { up20: 11, up50: 3, up100: 1, per_day: climatePeriod === '1D' ? 11 : 10.4, days: 20,
        basis: climatePeriod === '1D' ? 'same_minute' : 'per_session' },
      temperature: climatePeriod === '30D' ? 'normal' : 'hot', days,
      theme: { name: names[0], count: themes[names[0]], total, share_pct: Math.round((1000 * themes[names[0]]) / total) / 10,
        prev_share_pct: 21 },
      themes: names.map((name) => ({ name, count: themes[name], prev_count: Math.round(themes[name] * 0.7) })),
      gappers: { held: 7, total: 12, gone: 2, rate_pct: 58.3, baseline_rate_pct: 47 },
      halts: { count: 8, last: { symbol: 'RUNR', at: NOW - 11 * 60 }, by_side: null,
        by_side_why: 'the halt log does not record whether a halt was up or down' },
      top: [{ symbol: 'RUNR', change_pct: 212, date: '2026-10-12', price: 4.86, float_shares: 3_100_000,
        theme: 'Biotechnology', news_at: NOW - 2 * 3600 - 50 * 60 }],
    },
    top: { kind: p.top.kind, period: p.top.period, cards: topCards(p.top.kind, p.top.period), why: null },
    sources: [
      { id: 'ibkr', label: 'IBKR', ok: true, at: NOW, error: null },
      { id: 'ssga', label: 'State Street holdings', ok: true, at: NOW, error: null },
      { id: 'bea', label: 'BEA calendar', ok: true, at: NOW, error: null },
      { id: 'finnhub', label: 'Finnhub earnings', ok: true, at: NOW, error: null },
      { id: 'leaderboard', label: "Nova's scanner history", ok: true, at: NOW, error: null },
    ],
  };
}
