/**
 * The Cryptos page's wire, read defensively: a field that is missing or not the right kind is null (unknown),
 * never 0; an answer that is not the board at all (another schema version, not an object) is null and the page
 * says it could not read it.
 */
import type {
  BridgeRow,
  Candle,
  CandleSession,
  CoinWhy,
  CryptoBoard,
  CryptoCandles,
  CryptoCoin,
  CryptoClock,
  FearGreed,
  Lane,
  NewsKind,
  NewsRow,
  NextEvent,
  SourceStatus,
  Stablecoins,
} from './types';
import { CRYPTOS_SCHEMA_VERSION } from './constants';

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Obj => (isObj(v) ? v : {});

export function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() ? v : null;
}

function oneOf<T extends string>(v: unknown, allowed: readonly T[]): T | null {
  return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : null;
}

const KINDS = ['catalyst', 'negative', 'noise', 'news'] as const;

function lanes(v: unknown): Lane[] {
  return arr(v).flatMap((l) => {
    const a = num(arr(l)[0]);
    const b = num(arr(l)[1]);
    return a !== null && b !== null ? [[a, b] as Lane] : [];
  });
}

function clock(v: unknown): CryptoClock {
  const c = obj(v);
  const lane = obj(c.lanes);
  const next = obj(c.stock_next);
  const regions = obj(c.regions);
  const nextKind = oneOf(next.kind, ['premarket', 'open', 'close', 'after_hours_end'] as const);
  const nextAt = num(next.at);
  return {
    now: num(c.now) ?? Date.now() / 1000,
    stock_session: oneOf(c.stock_session, ['premarket', 'regular', 'after_hours', 'closed'] as const) ?? 'closed',
    stock_next: nextKind && nextAt !== null ? { kind: nextKind, at: nextAt } : null,
    crypto_day_start: num(c.crypto_day_start) ?? 0,
    crypto_day_start_et: str(c.crypto_day_start_et) ?? '20:00',
    regions: { asia: regions.asia === true, europe: regions.europe === true, us: regions.us === true },
    next_funding: num(c.next_funding) ?? 0,
    lanes: {
      asia: lanes(lane.asia),
      europe: lanes(lane.europe),
      premarket: lanes(lane.premarket),
      regular: lanes(lane.regular),
      after_hours: lanes(lane.after_hours),
      funding: lanes(lane.funding),
    },
  };
}

function fearGreed(v: unknown): FearGreed | null {
  const f = obj(v);
  const value = num(f.value);
  return value === null ? null : { value, label: str(f.label), week_ago: num(f.week_ago), at: num(f.at) };
}

function why(v: unknown): CoinWhy | null {
  const w = obj(v);
  const kind = oneOf(w.kind, KINDS);
  const title = str(w.title);
  return kind && title ? { kind, title, source: str(w.source), published_ts: num(w.published_ts), url: str(w.url) } : null;
}

function coin(v: unknown): CryptoCoin | null {
  const c = obj(v);
  const symbol = str(c.symbol);
  if (!symbol) return null;
  const ibkr = isObj(c.ibkr) && typeof c.ibkr.listed === 'boolean' ? { listed: c.ibkr.listed, venue: str(c.ibkr.venue) } : null;
  return {
    symbol,
    name: str(c.name) ?? symbol,
    rank: num(c.rank),
    price: num(c.price),
    high_24h: num(c.high_24h),
    low_24h: num(c.low_24h),
    change_1h_pct: num(c.change_1h_pct),
    change_24h_pct: num(c.change_24h_pct),
    change_7d_pct: num(c.change_7d_pct),
    volume_24h_usd: num(c.volume_24h_usd),
    volume_x_30d: num(c.volume_x_30d),
    market_cap_usd: num(c.market_cap_usd),
    from_ath_pct: num(c.from_ath_pct),
    spark_7d: arr(c.spark_7d).flatMap((p) => (num(p) === null ? [] : [num(p) as number])),
    funding_8h_pct: num(c.funding_8h_pct),
    groups: arr(c.groups).flatMap((g) => (typeof g === 'string' ? [g] : [])),
    why: why(c.why),
    news_checked: c.news_checked === true,
    ibkr,
    etf: str(c.etf),
    chart: c.chart === true,
  };
}

function bridgeRow(v: unknown): BridgeRow | null {
  const r = obj(v);
  const symbol = str(r.symbol);
  if (!symbol) return null;
  return {
    symbol,
    what: str(r.what) ?? '',
    driver: r.driver === 'ETH' ? 'ETH' : 'BTC',
    beta: num(r.beta),
    close: num(r.close),
    last: num(r.last),
    since_close_pct: num(r.since_close_pct),
    implied_pct: num(r.implied_pct),
    read: oneOf(r.read, ['ahead', 'behind', 'in_line'] as const),
    gap_pt: num(r.gap_pt),
  };
}

function stablecoins(v: unknown): Stablecoins | null {
  if (!isObj(v)) return null;
  return {
    supply_usd: num(v.supply_usd),
    change_7d_usd: num(v.change_7d_usd),
    daily: arr(v.daily).flatMap((d) => {
      const o = obj(d);
      const date = str(o.date);
      const net = num(o.net_usd);
      return date && net !== null ? [{ date, net_usd: net }] : [];
    }),
  };
}

function nextEvent(v: unknown): NextEvent | null {
  const e = obj(v);
  const at = num(e.at);
  const kind = oneOf(e.kind, ['funding', 'expiry', 'stocks', 'crypto_day'] as const);
  const title = str(e.title);
  return at !== null && kind && title ? { at, kind, title, detail: str(e.detail) } : null;
}

function newsRow(v: unknown): NewsRow | null {
  const n = obj(v);
  const ts = num(n.published_ts);
  const kind = oneOf(n.kind, KINDS) as NewsKind | null;
  const title = str(n.title);
  const symbol = str(n.symbol);
  return ts !== null && kind && title && symbol ? { published_ts: ts, symbol, kind, title, source: str(n.source), url: str(n.url) } : null;
}

const SOURCE_IDS = ['coingecko', 'coinbase', 'fear_greed', 'hyperliquid', 'defillama', 'deribit', 'alpaca', 'ibkr'] as const;

function source(v: unknown): SourceStatus | null {
  const s = obj(v);
  const id = oneOf(s.id, SOURCE_IDS);
  if (!id) return null;
  return { id, label: str(s.label) ?? id, ok: typeof s.ok === 'boolean' ? s.ok : null, at: num(s.at), error: str(s.error) };
}

const keep = <T,>(items: (T | null)[]): T[] => items.filter((x): x is T => x !== null);

export function normalizeBoard(raw: unknown): CryptoBoard | null {
  if (!isObj(raw) || raw.schema_version !== CRYPTOS_SCHEMA_VERSION) return null;
  const m = obj(raw.market);
  const lev = obj(raw.leverage);
  const flows = obj(raw.flows);
  const bridge = obj(raw.bridge);
  return {
    schema_version: CRYPTOS_SCHEMA_VERSION,
    generated_at: num(raw.generated_at) ?? 0,
    enabled: raw.enabled !== false,
    loading: raw.loading === true,
    replay_desk: raw.replay_desk === true,
    clock: clock(raw.clock),
    market: {
      total_cap_usd: num(m.total_cap_usd),
      total_cap_change_24h_pct: num(m.total_cap_change_24h_pct),
      btc_dominance_pct: num(m.btc_dominance_pct),
      btc_dominance_change_24h_pt: num(m.btc_dominance_change_24h_pt),
      total_volume_usd: num(m.total_volume_usd),
      volume_x_30d: num(m.volume_x_30d),
      fear_greed: fearGreed(m.fear_greed),
      eth_btc: num(m.eth_btc),
      eth_btc_change_24h_pct: num(m.eth_btc_change_24h_pct),
      btc_qqq_corr_30d: num(m.btc_qqq_corr_30d),
    },
    coins: keep(arr(raw.coins).map(coin)),
    leverage: {
      funding: arr(lev.funding).flatMap((f) => {
        const o = obj(f);
        const symbol = str(o.symbol);
        const rate = num(o.funding_8h_pct);
        return symbol && rate !== null ? [{ symbol, funding_8h_pct: rate }] : [];
      }),
      open_interest_usd: num(lev.open_interest_usd),
      btc_open_interest_usd: num(lev.btc_open_interest_usd),
      liquidations_24h: null,
      liquidations_note: str(lev.liquidations_note),
    },
    flows: { etf: null, etf_note: str(flows.etf_note), stablecoins: stablecoins(flows.stablecoins) },
    bridge: {
      reference_close_at: num(bridge.reference_close_at),
      phase: oneOf(bridge.phase, ['premarket', 'regular', 'after_hours', 'overnight'] as const) ?? 'overnight',
      btc_since_close_pct: num(bridge.btc_since_close_pct),
      eth_since_close_pct: num(bridge.eth_since_close_pct),
      rows: keep(arr(bridge.rows).map(bridgeRow)),
      error: str(bridge.error),
    },
    next: keep(arr(raw.next).map(nextEvent)),
    news: keep(arr(raw.news).map(newsRow)),
    sources: keep(arr(raw.sources).map(source)),
  };
}

function candle(v: unknown): Candle | null {
  const c = obj(v);
  const t = num(c.t);
  const o = num(c.o);
  const h = num(c.h);
  const l = num(c.l);
  const cl = num(c.c);
  return t !== null && o !== null && h !== null && l !== null && cl !== null ? { t, o, h, l, c: cl, v: num(c.v) } : null;
}

function session(v: unknown): CandleSession | null {
  const s = obj(v);
  const kind = oneOf(s.kind, ['premarket', 'regular', 'after_hours'] as const);
  const start = num(s.start);
  const end = num(s.end);
  return kind && start !== null && end !== null ? { kind, start, end } : null;
}

export function normalizeCandles(raw: unknown): CryptoCandles | null {
  if (!isObj(raw) || raw.schema_version !== CRYPTOS_SCHEMA_VERSION) return null;
  const lv = obj(raw.levels);
  const sc = obj(lv.stock_close);
  const scAt = num(sc.at);
  const scPx = num(sc.price);
  return {
    schema_version: CRYPTOS_SCHEMA_VERSION,
    symbol: str(raw.symbol) ?? '',
    tf: oneOf(raw.tf, ['15m', '1h', '4h', '1d'] as const) ?? '15m',
    product: str(raw.product),
    source: str(raw.source) ?? 'coinbase',
    loading: raw.loading === true,
    error: str(raw.error),
    candles: keep(arr(raw.candles).map(candle)),
    last: num(raw.last),
    change_24h_pct: num(raw.change_24h_pct),
    levels: {
      high_24h: num(lv.high_24h),
      low_24h: num(lv.low_24h),
      day_open: num(lv.day_open),
      day_open_at: num(lv.day_open_at),
      stock_close: scAt !== null && scPx !== null ? { at: scAt, price: scPx } : null,
    },
    sessions: keep(arr(raw.sessions).map(session)),
  };
}
