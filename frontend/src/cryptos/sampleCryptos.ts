/**
 * The Cryptos page on the sample desk (ADR 040): the approved mockup's figures, in the wire's own shape, at
 * Tue 2026-09-29 23:08 ET. Sample data like the rest of that desk -- nothing here is read from a source, and
 * what the live desk cannot know (liquidations, ETF flows) is unknown here too.
 */
import type { Candle, CryptoBoard, CryptoCandles, CryptoCoin, CandleTf } from './types';

const NOW = Date.UTC(2026, 8, 30, 3, 8) / 1000;          // Tue 23:08 ET
const REF = Date.UTC(2026, 8, 29, 20, 0) / 1000;         // Tue 16:00 ET
const DAY_OPEN = Date.UTC(2026, 8, 30, 0, 0) / 1000;     // 00:00 UTC = 20:00 ET

function rng(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A walk of ``n`` points from ``a`` to ``b`` (noise scaled to the distance), ending exactly on ``b``. */
function walk(r: () => number, a: number, b: number, n: number, noise: number): number[] {
  const out: number[] = [];
  let v = a;
  for (let i = 1; i <= n; i += 1) {
    v += (b - a) / n + (r() - 0.5) * noise;
    out.push(v);
  }
  const k = (b - a) / ((out[n - 1] - a) || 1);
  return out.map((x) => a + (x - a) * k);
}

/** A 7-day path (84 points, one every 2 h) that ends ``ch7d`` percent up and ``ch24h`` percent up on its last day. */
function path(seed: number, ch7d: number, ch24h: number): number[] {
  const r = rng(seed);
  const end = 100 * (1 + ch7d / 100);
  const dayAgo = end / (1 + ch24h / 100);
  return [100, ...walk(r, 100, dayAgo, 71, Math.max(1.2, Math.abs(ch7d) / 5)), ...walk(r, dayAgo, end, 12, Math.max(0.4, Math.abs(ch24h) / 6))];
}

type Row = [string, string, number, number, number, number, number, number, number, number, number | null,
  CryptoCoin['why'], boolean | null, string | null, string[], boolean];

const WHY = (kind: 'catalyst' | 'negative' | 'noise' | 'news', title: string, minsAgo: number): CryptoCoin['why'] => ({
  kind, title, source: 'Benzinga', published_ts: NOW - minsAgo * 60, url: null,
});

// symbol, name, price, 1h, 24h, 7d, volume, volume x, cap, from high, funding, why, IBKR lists, ETF, groups, chart
const ROWS: Row[] = [
  ['BTC', 'Bitcoin', 112480, 0.4, 2.84, 5.1, 38.2e9, 1.2, 2.24e12, -7.9, 0.012, WHY('catalyst', 'Spot ETFs took in $412M', 92), true, 'IBIT', ['major'], true],
  ['ETH', 'Ether', 4212.4, 0.9, 4.1, 8.7, 21.4e9, 1.5, 508e9, -14.8, 0.018, WHY('catalyst', 'Sixth day of ETF inflows', 70), true, 'ETHA', ['major', 'layer1'], true],
  ['SOL', 'Solana', 214.3, 1.6, 7.92, 12.4, 6.8e9, 2.1, 116e9, -27.0, 0.031, WHY('catalyst', 'Network upgrade went live', 27), true, null, ['major', 'layer1'], true],
  ['XRP', 'XRP', 2.941, -0.2, 1.12, -2.3, 4.1e9, 0.9, 175e9, -23.4, -0.004, null, true, null, ['major', 'payments'], true],
  ['BNB', 'BNB', 1012.5, 0.1, 0.84, 3.0, 1.9e9, 0.8, 141e9, -4.2, 0.006, null, false, null, ['major', 'layer1'], false],
  ['DOGE', 'Dogecoin', 0.2471, 2.3, 11.6, 18.9, 3.9e9, 3.4, 37.2e9, -66.3, 0.045, WHY('noise', 'Meme rotation, no news', 58), true, null, ['meme'], true],
  ['ADA', 'Cardano', 0.842, 0.5, 3.2, 1.1, 1.1e9, 1.1, 30.1e9, -72.6, 0.009, null, true, null, ['layer1'], true],
  ['LINK', 'Chainlink', 23.18, 0.3, 5.5, 9.8, 1.3e9, 1.6, 15.7e9, -55.1, 0.011, WHY('catalyst', 'Bank pilot announced', 140), false, null, ['defi'], true],
  ['SUI', 'Sui', 3.52, -1.8, -6.4, -11.2, 1.6e9, 2.6, 12.4e9, -35.2, -0.021, WHY('negative', 'Unlock Thu: 1.3% of supply', 243), false, null, ['layer1'], true],
  ['AVAX', 'Avalanche', 31.4, -0.6, 2.1, -4.4, 0.72e9, 1.0, 13.3e9, -78.0, 0.004, null, false, null, ['layer1'], true],
  ['BCH', 'Bitcoin Cash', 598.2, 0.0, 1.4, 2.2, 0.44e9, 0.8, 11.9e9, -84.3, 0.005, null, true, null, ['payments'], true],
  ['LTC', 'Litecoin', 112.6, 0.2, 1.9, 4.0, 0.61e9, 0.9, 8.6e9, -73.2, 0.007, null, true, null, ['payments'], true],
  ['PEPE', 'Pepe', 0.00001084, 3.1, 14.2, 22.5, 1.8e9, 4.1, 4.56e9, -61.0, 0.052, WHY('noise', 'Meme rotation, no news', 66), false, null, ['meme'], true],
];

const RANK_BY_CAP = new Map([...ROWS].sort((a, b) => b[8] - a[8]).map((row, i) => [row[0], i + 1]));

const COINS: CryptoCoin[] = ROWS.map(([symbol, name, p, c1, c24, c7, vol, vx, cap, ath, fund, why, listed, etf, groups, chart], i) => ({
  symbol, name, rank: RANK_BY_CAP.get(symbol) ?? null, price: p, high_24h: p * 1.006, low_24h: p * 0.969, change_1h_pct: c1,
  change_24h_pct: c24, change_7d_pct: c7, volume_24h_usd: vol, volume_x_30d: vx, market_cap_usd: cap,
  from_ath_pct: ath, spark_7d: path(11 + i, c7, c24).map((x) => (x / 100) * p / (1 + c7 / 100)),
  funding_8h_pct: fund, groups, why, news_checked: true,
  ibkr: listed === null ? null : { listed, venue: listed ? (['BTC', 'ETH', 'BCH', 'LTC'].includes(symbol) ? 'PAXOS' : 'ZEROHASH') : null },
  etf, chart,
}));

export const SAMPLE_CRYPTO_BOARD: CryptoBoard = {
  schema_version: 1,
  generated_at: NOW,
  enabled: true,
  loading: false,
  replay_desk: false,
  clock: {
    now: NOW,
    stock_session: 'closed',
    stock_next: { kind: 'premarket', at: NOW + 4 * 3600 + 52 * 60 },
    crypto_day_start: DAY_OPEN,
    crypto_day_start_et: '20:00',
    regions: { asia: true, europe: false, us: false },
    next_funding: NOW + 4 * 3600 + 52 * 60,
    lanes: {
      asia: [[0, 240], [1200, 1440]],
      europe: [[180, 690]],
      premarket: [[240, 570]],
      regular: [[570, 960]],
      after_hours: [[960, 1200]],
      funding: [[240, 240], [720, 720], [1200, 1200]],
    },
  },
  market: {
    total_cap_usd: 3.94e12,
    total_cap_change_24h_pct: 2.61,
    btc_dominance_pct: 57.8,
    btc_dominance_change_24h_pt: -0.4,
    total_volume_usd: 148.2e9,
    volume_x_30d: 1.31,
    fear_greed: { value: 68, label: 'Greed', week_ago: 54, at: NOW - 3 * 3600 },
    eth_btc: 0.03745,
    eth_btc_change_24h_pct: 1.2,
    btc_qqq_corr_30d: 0.61,
  },
  coins: COINS,
  leverage: {
    funding: [
      { symbol: 'PEPE', funding_8h_pct: 0.052 }, { symbol: 'DOGE', funding_8h_pct: 0.045 },
      { symbol: 'SOL', funding_8h_pct: 0.031 }, { symbol: 'ETH', funding_8h_pct: 0.018 },
      { symbol: 'BTC', funding_8h_pct: 0.012 }, { symbol: 'XRP', funding_8h_pct: -0.004 },
      { symbol: 'SUI', funding_8h_pct: -0.021 },
    ],
    open_interest_usd: 9.6e9,
    btc_open_interest_usd: 2.9e9,
    liquidations_24h: null,
    liquidations_note: 'No free source reachable from the desk reports liquidations; they need a paid aggregate (for example Coinglass).',
  },
  flows: {
    etf: null,
    etf_note: 'No free source publishes daily spot ETF flows as data; the chart shows stablecoin supply until one exists.',
    stablecoins: {
      supply_usd: 312.4e9,
      change_7d_usd: 2.1e9,
      daily: [142, -88, 236, 301, -164, 58, 189, 267, 343, 412].map((m, i) => ({
        date: `2026-09-${String(20 + i).padStart(2, '0')}`, net_usd: m * 1e6,
      })),
    },
  },
  bridge: {
    reference_close_at: REF,
    phase: 'overnight',
    btc_since_close_pct: 2.14,
    eth_since_close_pct: 3.02,
    rows: [
      { symbol: 'IBIT', what: 'BTC ETF', driver: 'BTC', beta: 1.0, close: 63.84, last: 65.05, since_close_pct: 1.9, implied_pct: 2.1, read: 'in_line', gap_pt: -0.2 },
      { symbol: 'ETHA', what: 'ETH ETF', driver: 'ETH', beta: 1.0, close: 31.62, last: 32.28, since_close_pct: 2.1, implied_pct: 3.0, read: 'behind', gap_pt: -0.9 },
      { symbol: 'MSTR', what: 'Holds BTC', driver: 'BTC', beta: 2.1, close: 398.2, last: 410.94, since_close_pct: 3.2, implied_pct: 4.5, read: 'behind', gap_pt: -1.3 },
      { symbol: 'COIN', what: 'Exchange', driver: 'BTC', beta: 1.6, close: 342.7, last: 356.75, since_close_pct: 4.1, implied_pct: 3.4, read: 'ahead', gap_pt: 0.7 },
      { symbol: 'MARA', what: 'Miner', driver: 'BTC', beta: 2.4, close: 21.34, last: 23.0, since_close_pct: 7.8, implied_pct: 5.1, read: 'ahead', gap_pt: 2.7 },
      { symbol: 'RIOT', what: 'Miner', driver: 'BTC', beta: 2.2, close: 15.92, last: 16.62, since_close_pct: 4.4, implied_pct: 4.7, read: 'in_line', gap_pt: -0.3 },
      { symbol: 'CLSK', what: 'Miner', driver: 'BTC', beta: 2.3, close: 13.05, last: null, since_close_pct: null, implied_pct: 4.9, read: null, gap_pt: null },
      { symbol: 'HOOD', what: 'Broker', driver: 'BTC', beta: 1.2, close: 128.4, last: 129.81, since_close_pct: 1.1, implied_pct: 2.6, read: 'behind', gap_pt: -1.5 },
    ],
    error: null,
  },
  next: [
    { at: NOW + 4 * 3600 + 52 * 60, kind: 'funding', title: 'Funding settles', detail: 'The 8-hour futures exchanges settle funding at 00:00, 08:00 and 16:00 UTC.' },
    { at: NOW + 4 * 3600 + 52 * 60, kind: 'stocks', title: 'US premarket opens', detail: null },
    { at: DAY_OPEN + 86400, kind: 'crypto_day', title: 'New crypto day', detail: 'Daily candles and 24-hour changes on most sites reset at 00:00 UTC.' },
    { at: Date.UTC(2026, 9, 2, 8, 0) / 1000, kind: 'expiry', title: 'Weekly options expiry', detail: 'BTC $4.1B open on Deribit' },
  ],
  news: [
    { published_ts: NOW - 27 * 60, symbol: 'SOL', kind: 'catalyst', title: 'Solana network upgrade goes live on mainnet', source: 'Benzinga', url: null },
    { published_ts: NOW - 92 * 60, symbol: 'BTC', kind: 'catalyst', title: 'Spot bitcoin ETFs log fifth straight inflow day', source: 'Benzinga', url: null },
    { published_ts: NOW - 243 * 60, symbol: 'SUI', kind: 'negative', title: 'Token unlock: 1.3% of supply releases Thursday', source: 'Benzinga', url: null },
    { published_ts: NOW - 58 * 60, symbol: 'DOGE', kind: 'noise', title: 'Why is Dogecoin rising today?', source: 'Benzinga', url: null },
  ],
  sources: [
    { id: 'coingecko', label: 'CoinGecko', ok: true, at: NOW - 12, error: null },
    { id: 'coinbase', label: 'Coinbase', ok: true, at: NOW - 8, error: null },
    { id: 'fear_greed', label: 'alternative.me', ok: true, at: NOW - 600, error: null },
    { id: 'hyperliquid', label: 'Hyperliquid', ok: true, at: NOW - 20, error: null },
    { id: 'defillama', label: 'DefiLlama', ok: true, at: NOW - 900, error: null },
    { id: 'deribit', label: 'Deribit', ok: true, at: NOW - 900, error: null },
    { id: 'alpaca', label: 'Alpaca news', ok: true, at: NOW - 60, error: null },
    { id: 'ibkr', label: 'IBKR', ok: true, at: NOW - 30, error: null },
  ],
};

/** Bitcoin's last 24 hours as the mockup drew them: a morning dip, the 16:00 close, the 21:30 breakout. */
function btcDay(): Candle[] {
  const anchors: [number, number][] = [
    [-0.75, 110900], [2, 110300], [4, 109700], [7, 109520], [9.5, 109150], [10.25, 108980], [12, 109800],
    [14, 109560], [16, 110120], [18, 111020], [20, 111640], [21.4, 113050], [22.5, 112260], [23.25, 112480],
  ];
  const at = (h: number): number => {
    for (let i = 1; i < anchors.length; i += 1) {
      const [h1, p1] = anchors[i];
      const [h0, p0] = anchors[i - 1];
      if (h <= h1) return p0 + ((p1 - p0) * (h - h0)) / (h1 - h0);
    }
    return anchors[anchors.length - 1][1];
  };
  const r = rng(7);
  const out: Candle[] = [];
  let prev = at(-0.75);
  const midnightEt = REF - 16 * 3600;
  for (let i = 0; i < 96; i += 1) {
    const hour = -0.75 + i * 0.25;
    const c = i === 95 ? 112480 : at(hour + 0.25) + (r() - 0.5) * 170;
    const o = i === 67 ? 110120 : prev;
    const busy = (hour >= 9.5 && hour < 10.75 ? 2.1 : 1) * (hour >= 21 && hour < 22.25 ? 3.2 : 1);
    out.push({ t: midnightEt + hour * 3600, o, h: Math.max(o, c) + r() * 110, l: Math.min(o, c) - r() * 110, c, v: (0.55 + r() * 0.7) * busy * 900 });
    prev = c;
  }
  const hi = out.reduce((a, b) => (b.h > a.h ? b : a));
  hi.h = 113120;
  const lo = out.reduce((a, b) => (b.l < a.l ? b : a));
  lo.l = 108960;
  return out;
}

const SCALE: Record<string, number> = { BTC: 1, ETH: 4212.4 / 112480, SOL: 214.3 / 112480, DOGE: 0.2471 / 112480 };

export function sampleCandles(symbol: string, tf: CandleTf): CryptoCandles {
  const k = SCALE[symbol] ?? (COINS.find((c) => c.symbol === symbol)?.price ?? 1) / 112480;
  const candles = btcDay().map((c) => ({ ...c, o: c.o * k, h: c.h * k, l: c.l * k, c: c.c * k }));
  return {
    schema_version: 1,
    symbol,
    tf,
    product: `${symbol}-USD`,
    source: 'coinbase',
    loading: false,
    error: null,
    candles,
    last: 112480 * k,
    change_24h_pct: 2.84,
    levels: {
      high_24h: 113120 * k,
      low_24h: 108960 * k,
      day_open: 111640 * k,
      day_open_at: DAY_OPEN,
      stock_close: { at: REF, price: 110120 * k },
    },
    sessions: [
      { kind: 'premarket', start: REF - 12 * 3600, end: REF - 6.5 * 3600 },
      { kind: 'regular', start: REF - 6.5 * 3600, end: REF },
      { kind: 'after_hours', start: REF, end: REF + 4 * 3600 },
    ],
  };
}
