/**
 * Nova Marketing Sample Data for the Global page (ADR 060): the approved v2 mockup's day (Tuesday 2026-10-20,
 * 11:12 ET), shown on the sample desk and the demo build. Nothing here is read live; the shape is the wire's.
 */
import type {
  Basis, Flow, GlobalBoard, Instrument, Market, Move, Period, Region, RegionId, SessionState, Sun, Totals,
} from './types';

const NOW = Date.UTC(2026, 9, 20, 15, 12, 30) / 1000;
const HOUR = 3600;

/** id, name, exchange, city, region, lat, lon, tz, UTC offset that day, sessions (local "HH:MM"), weekdays. */
type Row = [string, string, string, string, RegionId, number, number, string, number, [string, string][]];
const MARKETS: Row[] = [
  ['us', 'United States', 'NYSE + Nasdaq', 'New York', 'americas', 40.71, -74.01, 'America/New_York', -4, [['09:30', '16:00']]],
  ['ca', 'Canada', 'TSX', 'Toronto', 'americas', 43.65, -79.38, 'America/Toronto', -4, [['09:30', '16:00']]],
  ['br', 'Brazil', 'B3', 'São Paulo', 'americas', -23.55, -46.63, 'America/Sao_Paulo', -3, [['10:00', '17:00']]],
  ['uk', 'United Kingdom', 'LSE', 'London', 'europe', 51.51, -0.09, 'Europe/London', 1, [['08:00', '16:30']]],
  ['fr', 'France', 'Euronext Paris', 'Paris', 'europe', 48.86, 2.35, 'Europe/Paris', 2, [['09:00', '17:30']]],
  ['de', 'Germany', 'Xetra', 'Frankfurt', 'europe', 50.11, 8.68, 'Europe/Berlin', 2, [['09:00', '17:30']]],
  ['ch', 'Switzerland', 'SIX', 'Zurich', 'europe', 47.37, 8.54, 'Europe/Zurich', 2, [['09:00', '17:30']]],
  ['sa', 'Saudi Arabia', 'Tadawul', 'Riyadh', 'middle_east_africa', 24.71, 46.68, 'Asia/Riyadh', 3, [['10:00', '15:00']]],
  ['za', 'South Africa', 'JSE', 'Johannesburg', 'middle_east_africa', -26.2, 28.05, 'Africa/Johannesburg', 2, [['09:00', '17:00']]],
  ['in', 'India', 'NSE', 'Mumbai', 'asia_pacific', 19.07, 72.88, 'Asia/Kolkata', 5.5, [['09:15', '15:30']]],
  ['cn', 'China', 'SSE + SZSE', 'Shanghai', 'asia_pacific', 31.23, 121.47, 'Asia/Shanghai', 8, [['09:30', '11:30'], ['13:00', '15:00']]],
  ['hk', 'Hong Kong', 'HKEX', 'Hong Kong', 'asia_pacific', 22.28, 114.16, 'Asia/Hong_Kong', 8, [['09:30', '12:00'], ['13:00', '16:00']]],
  ['tw', 'Taiwan', 'TWSE', 'Taipei', 'asia_pacific', 25.03, 121.56, 'Asia/Taipei', 8, [['09:00', '13:30']]],
  ['kr', 'South Korea', 'KRX', 'Seoul', 'asia_pacific', 37.57, 126.98, 'Asia/Seoul', 9, [['09:00', '15:30']]],
  ['jp', 'Japan', 'JPX', 'Tokyo', 'asia_pacific', 35.68, 139.77, 'Asia/Tokyo', 9, [['09:00', '11:30'], ['12:30', '15:30']]],
  ['au', 'Australia', 'ASX', 'Sydney', 'asia_pacific', -33.87, 151.21, 'Australia/Sydney', 11, [['10:00', '16:00']]],
];

/** id -> [basis, symbol, label, exchange, currency, contract, multiplier, 1D money traded $, pressure %, move %, move basis]. */
const READS: Record<string, [Basis, string, string, string, string, string | null, number, number, number, number, Basis]> = {
  us: ['future', 'ES', 'S&P 500 futures', 'CME', 'USD', 'ESZ6', 50, 121e9, 8.2, 0.8, 'index'],
  ca: ['future', 'SXF', 'S&P/TSX 60 futures', 'CDE', 'CAD', 'SXFZ6', 200, 1.4e9, 4.1, 0.5, 'index'],
  br: ['etf', 'EWZ', 'EWZ (US-listed ETF)', 'SMART', 'USD', null, 1, 0.31e9, -6.4, -1.1, 'etf'],
  uk: ['future', 'Z', 'FTSE 100 futures', 'ICEEU', 'GBP', 'ZZ6', 10, 11.8e9, -5.6, 0.2, 'index'],
  fr: ['future', 'CAC40', 'CAC 40 futures', 'MONEP', 'EUR', 'FCEX6', 10, 8.9e9, -11.0, -0.6, 'index'],
  de: ['future', 'DAX', 'DAX futures', 'EUREX', 'EUR', 'FDAXZ6', 25, 31.5e9, -3.0, -0.4, 'index'],
  ch: ['future', 'SMI', 'SMI futures', 'EUREX', 'CHF', 'FSMIZ6', 10, 3.1e9, 2.9, 0.2, 'index'],
  sa: ['etf', 'KSA', 'KSA (US-listed ETF)', 'SMART', 'USD', null, 1, 0.024e9, 4.4, 0.3, 'etf'],
  za: ['etf', 'EZA', 'EZA (US-listed ETF)', 'SMART', 'USD', null, 1, 0.031e9, -2.3, -0.2, 'etf'],
  in: ['etf', 'INDA', 'INDA (US-listed ETF)', 'SMART', 'USD', null, 1, 0.42e9, 7.3, -0.2, 'index'],
  cn: ['future', 'XINA50', 'FTSE China A50 futures', 'SGX', 'USD', 'CNX26', 1, 14e9, -14.2, -1.6, 'index'],
  hk: ['future', 'HSI', 'Hang Seng futures', 'HKFE', 'HKD', 'HSIX6', 50, 26e9, -11.4, -1.8, 'index'],
  tw: ['etf', 'EWT', 'EWT (US-listed ETF)', 'SMART', 'USD', null, 1, 0.36e9, 9.1, 1.1, 'etf'],
  kr: ['future', 'K200', 'KOSPI 200 futures', 'KSE', 'KRW', '101Z6', 250000, 14e9, 5.2, -0.3, 'index'],
  jp: ['future', 'N225', 'Nikkei 225 futures', 'OSE.JPN', 'JPY', 'N225Z6', 1000, 24.8e9, -2.0, 0.7, 'index'],
  au: ['future', 'AP', 'SPI 200 futures', 'SNFE', 'AUD', 'APZ6', 25, 3.9e9, -2.1, -0.2, 'index'],
};

const INDEX_LABEL: Record<string, string> = {
  us: 'S&P 500', ca: 'S&P/TSX Composite', uk: 'FTSE 100', fr: 'CAC 40', de: 'DAX', ch: 'SMI', in: 'Nifty 50',
  cn: 'FTSE China A50', hk: 'Hang Seng', kr: 'KOSPI 200', jp: 'Nikkei 225', au: 'S&P/ASX 200',
};

const REGION_LABEL: Record<RegionId, string> = {
  americas: 'Americas', europe: 'Europe', middle_east_africa: 'Middle East & Africa', asia_pacific: 'Asia-Pacific',
};

const FX: Record<string, number> = {
  CAD: 0.7241, GBP: 1.3352, EUR: 1.1638, CHF: 1.2531, HKD: 0.1287, KRW: 0.000703, JPY: 0.00662, AUD: 0.6612,
};

function segments(offset: number, sessions: [string, string][]): [number, number][] {
  return sessions.map(([a, b]) => {
    const at = (hm: string) => {
      const [h, m] = hm.split(':').map(Number);
      return Date.UTC(2026, 9, 20, 0, 0) / 1000 + (h - offset) * HOUR + m * 60;
    };
    return [at(a), at(b)];
  });
}

function state(segs: [number, number][]): SessionState {
  if (segs.some(([a, b]) => a <= NOW && NOW < b)) return 'open';
  if (segs[0][0] <= NOW && NOW < segs[segs.length - 1][1]) return 'break';
  return 'closed';
}

function instrument(kind: Basis, symbol: string, label: string, exchange: string, currency: string,
  contract: string | null, multiplier: number | null): Instrument {
  return { kind, symbol, label, exchange, currency, contract, multiplier };
}

const SCALE: Record<Period, [number, number, number]> = { '1D': [1, 1, 1], '7D': [5.4, 0.7, 2.1], '30D': [22, 0.45, 3.4] };
/** 7 D / 30 D turn a few markets round so the longer view reads differently (the mockup's days). */
const LONGER_FLIP: Record<Period, string[]> = { '1D': [], '7D': ['uk', 'ch', 'kr'], '30D': ['uk', 'fr', 'hk', 'sa'] };

/** A country ETF trades in the US regular session. */
const US_SEGMENTS = segments(-4, [['09:30', '16:00']]);

function flow(id: string, period: Period, own: [number, number][]): Flow {
  const [basis, symbol, label, exchange, currency, contract, mult, traded1, p1] = READS[id];
  const segs = basis === 'etf' ? US_SEGMENTS : own;
  const [tradedX, pressureX] = SCALE[period];
  const p = (LONGER_FLIP[period].includes(id) ? -1 : 1) * p1 * pressureX;
  const traded = traded1 * tradedX;
  const up = traded * (0.45 + p / 200);
  const down = traded * (0.45 - p / 200);
  const longer = period !== '1D';
  return {
    basis, instrument: instrument(basis, symbol, label, exchange, currency, contract, mult),
    from: longer ? (period === '7D' ? '2026-10-14' : '2026-09-22') : segs[0][0],
    to: longer ? '2026-10-20' : segs[segs.length - 1][1],
    bars: longer ? null : Math.round((Math.min(NOW, segs[segs.length - 1][1]) - segs[0][0]) / 60),
    sessions: longer ? (period === '7D' ? 5 : 21) : null,
    up_usd: up, down_usd: down, flat_usd: traded * 0.1, traded_usd: traded, pressure_usd: up - down,
    pressure_pct: Math.round(p * 100) / 100, last_bar_at: longer ? null : Math.min(NOW - 30, segs[segs.length - 1][1] - 60),
    fx: currency === 'USD' ? null : { currency, usd_per_unit: FX[currency], date: '2026-10-19' },
    at: NOW - 40, error: null, refused: [],
  };
}

function move(id: string, period: Period): Move {
  const [basis, symbol, label, exchange, currency, contract, mult, , , m1, moveBasis] = READS[id];
  const pct = (LONGER_FLIP[period].includes(id) ? -1 : 1) * m1 * SCALE[period][2];
  const inst = moveBasis === 'index'
    ? instrument('index', id.toUpperCase(), INDEX_LABEL[id] ?? label, exchange, currency, null, null)
    : instrument(basis, symbol, label, exchange, currency, contract, mult);
  return { basis: moveBasis, instrument: inst, pct: Math.round(pct * 100) / 100, last: null, prev_close: null,
    at: NOW - 20, data_type: 'live', error: null };
}

function totals(rows: Market[]): Totals {
  const known = rows.filter((r) => r.flow.pressure_usd != null);
  const up = known.reduce((a, r) => a + (r.flow.up_usd ?? 0), 0);
  const down = known.reduce((a, r) => a + (r.flow.down_usd ?? 0), 0);
  const traded = known.reduce((a, r) => a + (r.flow.traded_usd ?? 0), 0);
  const moves = rows.map((r) => r.move.pct).filter((v): v is number => v != null);
  return {
    pressure_usd: up - down, traded_usd: traded, pressure_pct: traded ? Math.round(((up - down) / traded) * 10000) / 100 : null,
    markets: rows.length, flows: known.length, up: moves.filter((v) => v > 0).length, down: moves.filter((v) => v < 0).length,
    avg_move_pct: moves.length ? Math.round((moves.reduce((a, v) => a + v, 0) / moves.length) * 1000) / 1000 : null,
  };
}

/** Net money by the hour over the last 24 hours (the mockup's day: Asia sold its close, the US open bought). */
const SUN_NET: [number, RegionId][] = [
  [0.4, 'americas'], [0.2, 'americas'], [0.1, 'americas'], [0.6, 'americas'], [0, 'americas'], [0, 'americas'],
  [0, 'americas'], [0, 'americas'], [0.9, 'asia_pacific'], [1.4, 'asia_pacific'], [-0.6, 'asia_pacific'],
  [-2.1, 'asia_pacific'], [-3.0, 'asia_pacific'], [-1.9, 'asia_pacific'], [-0.8, 'asia_pacific'],
  [-0.9, 'europe'], [-1.3, 'europe'], [-1.1, 'europe'], [-0.7, 'europe'], [-0.4, 'europe'], [0.2, 'europe'],
  [-0.3, 'europe'], [2.9, 'americas'], [3.6, 'americas'],
];

function sun(rows: Market[]): Sun {
  const to = NOW - (NOW % HOUR) + HOUR;
  const from = to - 24 * HOUR;
  const hours = SUN_NET.map(([b, region], i) => ({
    t: from + i * HOUR, net_usd: b * 1e9, traded_usd: Math.abs(b) * 1e9 * 9 + 2e9, markets: b ? 3 : 0,
    by_region: b ? { [region]: b * 1e9 } : {},
  }));
  const sessions = rows.flatMap((r) => r.session.segments
    .flatMap(([a, b]) => [[a, b], [a - 24 * HOUR, b - 24 * HOUR]] as [number, number][])
    .filter(([a, b]) => b > from && a < to)
    .map(([a, b]) => ({ market: r.id, region: r.region, start: Math.max(a, from), end: Math.min(b, to) })));
  return { from, to, now: NOW, hours, sessions };
}

export function sampleGlobalBoard(period: Period = '1D'): GlobalBoard {
  const markets: Market[] = MARKETS.map(([id, name, exchange, city, region, lat, lon, tz, offset, sessions]) => {
    const segs = segments(offset, sessions);
    const f = flow(id, period, segs);
    const m = move(id, period);
    const mixed = f.pressure_pct != null && m.pct != null && Math.abs(f.pressure_pct) >= 5 && Math.abs(m.pct) >= 0.15
      && f.pressure_pct > 0 !== m.pct > 0;
    return {
      id, name, exchange, city, region, lat, lon, tz,
      session: { date: '2026-10-20', state: state(segs), open_at: segs[0][0], close_at: segs[segs.length - 1][1],
        segments: segs, next_open_at: segs[0][0] + 24 * HOUR, calendar: id === 'us' ? 'nyse' : 'clock' },
      move: m, flow: f, mixed,
    };
  });
  const regions: Region[] = (Object.keys(REGION_LABEL) as RegionId[]).map((id) => ({
    id, label: REGION_LABEL[id], ...totals(markets.filter((r) => r.region === id)),
  }));
  return {
    schema_version: 1, generated_at: NOW, enabled: true, loading: false, replay_desk: false, period,
    read: {
      verdict: 'rotation', headline: 'Rotation, not an exit', detail: 'Asia-Pacific sold, Americas bought',
      rule: 'Money in at +5% of the money that traded, money out at -5%; otherwise rotation when regions pull apart.',
    },
    world: totals(markets), regions, markets, sun: sun(markets),
    sources: [{ id: 'ibkr', label: 'IBKR', ok: true, at: NOW - 5, error: null }],
    budget: { history_left: 41, history_headroom: 40, waiting: null },
  };
}
