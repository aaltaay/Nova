/**
 * Nova Marketing Sample Data for the Forex page (ADR 062): the approved mockup v2's day (Tuesday 2026-10-20, 11:12 ET,
 * the Global page's sample moment), shown on the sample desk and the demo build. The market's size is the BIS
 * survey's real figures (as on the live page); every rate, move and futures figure is sample. Each currency's move
 * against the dollar, by session, drives strength, the sessions, the pairs and the read by the backend's arithmetic.
 */
import { MAJORS } from './constants';
import { cross, strengths } from './cross';
import type {
  Currency, ForexBoard, Futures, Home, Period, Price, Read, Session, SessionId, Sun, SunHour,
} from './types';

const HOUR = 3600;
const NOW = Date.UTC(2026, 9, 20, 15, 12, 30) / 1000;
const DAY0 = Date.UTC(2026, 9, 19, 21, 0) / 1000;            // Monday 17:00 ET
const DONE = (NOW - DAY0) / HOUR;
const BEGUN = Math.ceil(DONE);

const BIS_TOTAL = 9_510.24e9;
const DESKS: [string, number][] = [
  ['UK', 4_742.575e9], ['US', 2_334.7e9], ['Singapore', 1_485.282e9], ['Hong Kong', 883.067e9], ['Japan', 440.231e9],
  ['Germany', 386.077e9], ['Switzerland', 370.472e9], ['France', 242.217e9], ['China', 235.05e9], ['Other', 1_437.443e9],
];
const DESKS_TOTAL = DESKS.reduce((a, [, v]) => a + v, 0);
const REGIONS = { asia_pacific: 3_526e9, europe: 6_247e9, americas: 2_648e9 };

/** code, name, city, lat, lon, tz, BIS $ a day, rank, biggest pair, its $ a day. */
type Row = [string, string, string, number, number, string, number, number, string, number];
const CURRENCIES: Row[] = [
  ['USD', 'US dollar', 'New York', 40.71, -74.01, 'America/New_York', 8_472e9, 1, 'EUR/USD', 1_970.331e9],
  ['EUR', 'Euro', 'Frankfurt', 50.11, 8.68, 'Europe/Berlin', 2_714e9, 2, 'EUR/USD', 1_970.331e9],
  ['JPY', 'Japanese yen', 'Tokyo', 35.68, 139.77, 'Asia/Tokyo', 1_608e9, 3, 'USD/JPY', 1_370.104e9],
  ['GBP', 'British pound', 'London', 51.51, -0.09, 'Europe/London', 967e9, 4, 'GBP/USD', 715.489e9],
  ['CNY', 'Chinese yuan', 'Shanghai', 31.23, 121.47, 'Asia/Shanghai', 817e9, 5, 'USD/CNY', 781.309e9],
  ['CHF', 'Swiss franc', 'Zurich', 47.37, 8.54, 'Europe/Zurich', 601e9, 6, 'USD/CHF', 455.18e9],
  ['AUD', 'Australian dollar', 'Sydney', -33.87, 151.21, 'Australia/Sydney', 582e9, 7, 'AUD/USD', 467.113e9],
  ['CAD', 'Canadian dollar', 'Toronto', 43.65, -79.38, 'America/Toronto', 547e9, 8, 'USD/CAD', 491.602e9],
  ['HKD', 'Hong Kong dollar', 'Hong Kong', 22.28, 114.16, 'Asia/Hong_Kong', 367e9, 9, 'USD/HKD', 346.691e9],
  ['SGD', 'Singapore dollar', 'Singapore', 1.29, 103.85, 'Asia/Singapore', 232e9, 10, 'USD/SGD', 214.691e9],
  ['INR', 'Indian rupee', 'Mumbai', 19.07, 72.88, 'Asia/Kolkata', 185e9, 11, 'USD/INR', 181.313e9],
  ['KRW', 'Korean won', 'Seoul', 37.57, 126.98, 'Asia/Seoul', 171e9, 12, 'USD/KRW', 165.352e9],
  ['SEK', 'Swedish krona', 'Stockholm', 59.33, 18.07, 'Europe/Stockholm', 158e9, 13, 'USD/SEK', 104.806e9],
  ['NZD', 'New Zealand dollar', 'Wellington', -41.29, 174.78, 'Pacific/Auckland', 147e9, 14, 'NZD/USD', 118.687e9],
  ['MXN', 'Mexican peso', 'Mexico City', 19.43, -99.13, 'America/Mexico_City', 147e9, 15, 'USD/MXN', 133.919e9],
  ['NOK', 'Norwegian krone', 'Oslo', 59.91, 10.75, 'Europe/Oslo', 127e9, 16, 'USD/NOK', 85.341e9],
  ['TWD', 'Taiwan dollar', 'Taipei', 25.03, 121.56, 'Asia/Taipei', 116e9, 17, 'USD/TWD', 113.62e9],
  ['BRL', 'Brazilian real', 'São Paulo', -23.55, -46.63, 'America/Sao_Paulo', 90e9, 18, 'USD/BRL', 85.893e9],
  ['ZAR', 'South African rand', 'Johannesburg', -26.2, 28.05, 'Africa/Johannesburg', 82e9, 19, 'USD/ZAR', 74.94e9],
];

/** The pair as quoted, its rate now, quoted per dollar?, and the currency's move against the dollar by session. */
const SPOT: Record<string, [string, number, boolean, [number, number, number]]> = {
  EUR: ['EUR/USD', 1.1638, false, [0.03, -0.17, -0.04]], JPY: ['USD/JPY', 150.42, true, [0.3, 0.04, 0.08]],
  GBP: ['GBP/USD', 1.3311, false, [0, 0.08, -0.39]], CNY: ['USD/CNH', 7.1318, true, [-0.06, 0.01, 0.01]],
  CHF: ['USD/CHF', 0.7969, true, [0.02, 0.1, 0.02]], AUD: ['AUD/USD', 0.6574, false, [-0.4, -0.08, -0.1]],
  CAD: ['USD/CAD', 1.3843, true, [-0.02, -0.04, -0.16]], HKD: ['USD/HKD', 7.7712, true, [0, -0.01, 0]],
  SGD: ['USD/SGD', 1.2954, true, [-0.07, -0.02, -0.03]], SEK: ['USD/SEK', 9.412, true, [-0.02, -0.23, -0.1]],
  NZD: ['NZD/USD', 0.5941, false, [-0.35, -0.06, -0.08]], MXN: ['USD/MXN', 18.531, true, [-0.1, -0.16, -0.4]],
  NOK: ['USD/NOK', 10.084, true, [-0.03, -0.25, -0.16]], BRL: ['USD/BRL', 5.412, true, [0, -0.1, -0.61]],
  ZAR: ['USD/ZAR', 17.86, true, [-0.15, -0.38, -0.3]],
};
const FROM_FUTURES = new Set(['BRL']);
const NO_PRICE = 'IBKR has no spot quote for this pair (sample)';

/** CME code, front contract, multiplier, label, traded today $, pressure %, inverted, and buyers' lean by session. */
const FUT: Record<string, [string, string, number, string, number, number, boolean, [number, number, number]]> = {
  EUR: ['6E', 'EURZ6', 125_000, 'Euro FX futures (6E)', 19.6e9, -5.1, false, [0.05, -0.55, -0.15]],
  JPY: ['6J', 'JPYZ6', 12_500_000, 'Japanese yen futures (6J)', 12.8e9, 13.6, false, [0.6, 0.1, 0.05]],
  GBP: ['6B', 'GBPZ6', 62_500, 'British pound futures (6B)', 7.4e9, -4.2, false, [0, 0.3, -0.45]],
  CHF: ['6S', 'CHFZ6', 125_000, 'Swiss franc futures (6S)', 2.3e9, -6.4, false, [-0.1, -0.45, -0.1]],
  CAD: ['6C', 'CADZ6', 100_000, 'Canadian dollar futures (6C)', 5.1e9, -3, false, [-0.1, -0.1, -0.2]],
  AUD: ['6A', 'AUDZ6', 100_000, 'Australian dollar futures (6A)', 6.2e9, -12.4, false, [-0.6, -0.25, -0.1]],
  NZD: ['6N', 'NZDZ6', 100_000, 'New Zealand dollar futures (6N)', 1.5e9, -9.8, false, [-0.5, -0.2, 0]],
  CNY: ['CNH', 'CNHZ6', 100_000, 'USD/offshore yuan futures (CNH)', 0.09e9, -4, true, [-0.3, -0.1, 0]],
  MXN: ['6M', 'MXPZ6', 500_000, 'Mexican peso futures (6M)', 2.7e9, 7.1, false, [0, -0.1, 0.45]],
  BRL: ['6L', 'BREZ6', 100_000, 'Brazilian real futures (6L)', 0.24e9, -12.9, false, [0, 0, -0.5]],
  ZAR: ['6Z', 'ZARZ6', 500_000, 'South African rand futures (6Z)', 0.03e9, -8, false, [0, -0.3, -0.2]],
};
/** Today's range over a normal day's, and the futures' volume so far over a normal day's. */
const ACTIVITY: Record<string, [number, number | null]> = {
  EUR: [1.1, 0.8], JPY: [1.6, 1.0], GBP: [1.3, 0.7], CNY: [0.8, 0.6], CHF: [1.4, 0.9], AUD: [1.5, 1.1],
  CAD: [1.0, 0.6], HKD: [0.6, null], SGD: [0.9, null], SEK: [1.2, null], NZD: [1.4, 0.9], MXN: [1.7, 1.2],
  NOK: [1.3, null], BRL: [1.5, 1.0], ZAR: [1.8, 0.7],
};

const BASE: Record<number, number> = {
  17: 0.6, 18: 1, 19: 2, 20: 3.5, 21: 3.5, 22: 2.5, 23: 2, 0: 1.5, 1: 1.5, 2: 2.5, 3: 5.5, 4: 5, 5: 4, 6: 3.5, 7: 4.5,
  8: 9, 9: 11, 10: 11, 11: 8, 12: 6, 13: 5, 14: 5, 15: 4, 16: 2.5,
};
/** The sessions' hours of the day: Asia 17:00-03:00 ET, London 03:00-08:00, New York 08:00-17:00 (that week). */
const BLOCKS: [SessionId, string, number, number][] = [['asia', 'Asia', 0, 10], ['london', 'London', 10, 15], ['new_york', 'New York', 15, 24]];
const blockOf = (h: number) => (h < 10 ? 0 : h < 15 ? 1 : 2);
const weight = (h: number) => BASE[(17 + h) % 24] * Math.max(0.05, Math.min(1, DONE - h));

/** Each priced currency's move against the dollar at the end of each hour begun, the session totals exact. */
function paths(): Record<string, number[]> {
  const out: Record<string, number[]> = { USD: Array(BEGUN).fill(0) };
  Object.entries(SPOT).forEach(([code, [, , , drift]], k) => {
    const steps = Array(BEGUN).fill(0) as number[];
    for (let b = 0; b < 3; b += 1) {
      const hrs = [...Array(BEGUN).keys()].filter((h) => blockOf(h) === b);
      if (!hrs.length) continue;
      const w = hrs.map(weight);
      const sumW = w.reduce((a, x) => a + x, 0);
      const wig = hrs.map((h) => 0.3 * Math.abs(drift[b]) * Math.sin(h * 1.7 + k) / Math.sqrt(hrs.length));
      const meanWig = wig.reduce((a, x) => a + x, 0) / wig.length;
      hrs.forEach((h, i) => { steps[h] = (drift[b] * w[i]) / sumW + (wig[i] - meanWig); });
    }
    let level = 0;
    out[code] = steps.map((s) => (level += s));
  });
  return out;
}

const PATHS = paths();
const PRICED = Object.keys(PATHS);
const strengthAt = (h: number): Record<string, number> =>
  strengths(Object.fromEntries(PRICED.map((c) => [c, h < 0 ? 0 : PATHS[c][Math.min(h, BEGUN - 1)]])));
const PATH = [...Array(BEGUN).keys()].map(strengthAt);

function blockChange(code: string, b: number): number | null {
  const [, , h0, h1] = BLOCKS[b];
  if (h0 >= BEGUN) return null;
  const end = PATH[Math.min(h1, BEGUN) - 1][code];
  const start = h0 > 0 ? PATH[h0 - 1][code] : 0;
  return end - start;
}

/** Futures money by hour: [net $, traded $] per hour begun, from the currency's side. */
function futuresHours(code: string): [number, number][] {
  const [, , , , traded, pct, , lean] = FUT[code];
  const w = [...Array(BEGUN).keys()].map((h) => (h === 0 ? 0 : weight(h)));
  const sumW = w.reduce((a, x) => a + x, 0);
  const tr = w.map((x) => (traded * x) / sumW);
  const d = tr.map((_t, h) => lean[blockOf(h)] + 0.2 * Math.sin(h * 2.3 + code.charCodeAt(0)));
  const unscaled = tr.reduce((a, t, h) => a + t * d[h], 0);
  const k = (pct / 100) * traded / unscaled;
  return tr.map((t, h) => [t * d[h] * k, t]);
}

const FUT_HOURS = Object.fromEntries(Object.keys(FUT).map((c) => [c, futuresHours(c)]));

/** The longer periods: moves x, traded x, pressure x, and the currencies whose week or month went the other way. */
const LONGER: Record<Period, [number, number, number, string[]]> = {
  '1D': [1, 1, 1, []], '7D': [2.1, 5.4, 0.7, ['GBP', 'CHF', 'CAD']], '30D': [3.4, 22, 0.45, ['GBP', 'EUR', 'NZD', 'MXN']],
};

function vsUsd(code: string, period: Period): number | null {
  if (!SPOT[code]) return code === 'USD' ? 0 : null;
  const today = PATHS[code][BEGUN - 1];
  const [moveX, , , flips] = LONGER[period];
  return (flips.includes(code) ? -1 : 1) * today * moveX;
}

function pairMove(perUsd: boolean, vs: number): number {
  return perUsd ? (1 / (1 + vs / 100) - 1) * 100 : vs;
}

function localParts(ts: number, tz: string): { day: number; minutes: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date(ts * 1000));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  const day = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(get('weekday'));
  return { day, minutes: (Number(get('hour')) % 24) * 60 + Number(get('minute')) };
}

function home(tz: string): Home {
  const { day, minutes } = localParts(NOW, tz);
  const weekday = day >= 1 && day <= 5;
  const open = weekday && minutes >= 480 && minutes < 1020;
  const startOfDay = NOW - minutes * 60;
  const openAt = weekday ? startOfDay + 480 * 60 : null;
  const closeAt = weekday ? startOfDay + 1020 * 60 : null;
  let next: number | null = null;
  for (let ahead = 0; ahead < 4 && next == null; ahead += 1) {
    const at = startOfDay + ahead * 86400 + 480 * 60;
    if (at > NOW && ((day + ahead) % 7) >= 1 && ((day + ahead) % 7) <= 5) next = at;
  }
  return { open, open_at: openAt, close_at: closeAt, next_open_at: next };
}

function price(code: string, period: Period): Price {
  const spot = SPOT[code];
  if (!spot) {
    return { basis: code === 'USD' ? 'spot' : null, instrument: null, pair: code === 'USD' ? null : `USD/${code}`, rate: null,
      open: null, pair_pct: code === 'USD' ? 0 : null, vs_usd_pct: code === 'USD' ? 0 : null, at: code === 'USD' ? NOW - 20 : null,
      data_type: null, error: code === 'USD' ? null : NO_PRICE };
  }
  const [quote, rate, perUsd] = spot;
  const vs = vsUsd(code, period) as number;
  const pm = pairMove(perUsd, vs);
  const basis = FROM_FUTURES.has(code) ? 'future' : 'spot';
  const inst = basis === 'future'
    ? { kind: 'future' as const, symbol: 'BRE', label: FUT.BRL[3], exchange: 'CME', currency: 'USD', contract: FUT.BRL[1], multiplier: FUT.BRL[2] }
    : { kind: 'spot' as const, symbol: quote.replace('/', ''), label: `${quote} spot (IDEALPRO)`, exchange: 'IDEALPRO', currency: quote.slice(4), contract: null, multiplier: null };
  return { basis, instrument: inst, pair: quote, rate, open: rate / (1 + pm / 100), pair_pct: pm, vs_usd_pct: vs,
    at: NOW - 20, data_type: basis === 'spot' ? 'live' : null, error: null };
}

const EMPTY_FUTURES: Futures = {
  basis: null, instrument: null, inverted: null, traded_usd: null, up_usd: null, down_usd: null, pressure_usd: null,
  pressure_pct: null, contracts: null, last_bar_at: null, at: null, error: 'no CME future', refused: [],
};

function futures(code: string, period: Period): Futures {
  const f = FUT[code];
  if (!f) return EMPTY_FUTURES;
  const [symbol, contract, mult, label, traded1, pct1, inverted] = f;
  const [, tradedX, pressureX, flips] = LONGER[period];
  const traded = traded1 * tradedX;
  const pct = (flips.includes(code) ? -1 : 1) * pct1 * pressureX;
  const up = traded * (0.45 + pct / 200);
  const down = traded * (0.45 - pct / 200);
  return {
    basis: 'future', inverted,
    instrument: { kind: 'future', symbol, label, exchange: 'CME', currency: inverted ? 'CNH' : 'USD', contract, multiplier: mult },
    traded_usd: traded, up_usd: up, down_usd: down, pressure_usd: up - down, pressure_pct: Math.round(pct * 100) / 100,
    contracts: null, last_bar_at: period === '1D' ? NOW - 30 : null, at: NOW - 40, error: null, refused: [],
  };
}

function dollarFutures(rows: Currency[]): Futures {
  const got = rows.map((r) => r.futures).filter((f) => f.traded_usd != null);
  const traded = got.reduce((a, f) => a + (f.traded_usd ?? 0), 0);
  const up = got.reduce((a, f) => a + (f.down_usd ?? 0), 0);
  const down = got.reduce((a, f) => a + (f.up_usd ?? 0), 0);
  return { ...EMPTY_FUTURES, basis: 'sum', traded_usd: traded, up_usd: up, down_usd: down, pressure_usd: up - down,
    pressure_pct: Math.round(((up - down) / traded) * 10000) / 100, at: NOW - 40, error: null };
}

function readOf(strength: Record<string, number>, period: Period): Read {
  const [g, d] = { '1D': [0.15, 0.2], '7D': [0.4, 0.5], '30D': [0.8, 1] }[period];
  const mean = (cs: string[]) => {
    const v = cs.filter((c) => c in strength).map((c) => strength[c]);
    return v.length ? v.reduce((a, x) => a + x, 0) / v.length : null;
  };
  const safe = mean(['JPY', 'CHF']);
  const risky = mean(['AUD', 'NZD', 'CAD', 'NOK', 'SEK', 'MXN', 'ZAR', 'BRL']);
  const usd = strength.USD ?? 0;
  const verdict = safe != null && risky != null && safe >= g && risky <= -g ? 'safe_havens'
    : safe != null && risky != null && safe <= -g && risky >= g ? 'risk_on'
      : usd >= d ? 'dollar_bought' : usd <= -d ? 'dollar_sold' : 'quiet';
  const headline = { safe_havens: 'Safe havens bought', risk_on: 'Riskier currencies bought', dollar_bought: 'Dollar bought',
    dollar_sold: 'Dollar sold', quiet: 'Quiet' }[verdict];
  const ranked = Object.keys(strength).filter((c) => c !== 'HKD').sort((a, b) => strength[b] - strength[a]);
  const rose = ranked.slice(0, 3);
  const word: Record<string, string> = { USD: 'the dollar', EUR: 'the euro', JPY: 'the yen', GBP: 'the pound', CNY: 'the yuan',
    CHF: 'the franc', AUD: 'the Australian dollar', CAD: 'the Canadian dollar', SGD: 'the Singapore dollar', SEK: 'the krona',
    NZD: 'the New Zealand dollar', MXN: 'the peso', NOK: 'the krone', BRL: 'the real', ZAR: 'the rand' };
  const names = rose.map((c) => word[c] ?? c);
  return {
    verdict, headline, detail: `Money ran to ${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`,
    rose, fell: ranked.slice(-3).reverse(),
    rule: 'Safe havens bought when the yen and the franc rise and the riskier currencies fall; else the dollar bought or sold; else quiet.',
  };
}

function sessionsOf(): Session[] {
  const share = (k: SessionId) => (k === 'asia' ? REGIONS.asia_pacific : k === 'london' ? DESKS[0][1] : DESKS[1][1]) / DESKS_TOTAL * 100;
  return BLOCKS.map(([id, name, h0, h1], b) => {
    const moves = PRICED.filter((c) => c !== 'HKD').map((c) => [c, blockChange(c, b) ?? 0] as [string, number]);
    const rose = moves.reduce((a, m) => (m[1] > a[1] ? m : a));
    const fell = moves.reduce((a, m) => (m[1] < a[1] ? m : a));
    const from = DAY0 + h0 * HOUR;
    const to = DAY0 + h1 * HOUR;
    return {
      id, name, from, to, state: NOW < from ? 'later' : NOW < to ? 'now' : 'done',
      rose: { code: rose[0], pct: rose[1] }, fell: { code: fell[0], pct: fell[1] },
      desks: { label: id === 'asia' ? 'desks in Asia' : id === 'london' ? 'UK desks' : 'US desks', share_pct: Math.round(share(id) * 10) / 10 },
    };
  });
}

function sunOf(): Sun {
  const hours: SunHour[] = PATH.map((row, h) => {
    const prev = h ? PATH[h - 1] : {};
    const strength = Object.fromEntries(Object.entries(row).map(([c, v]) => [c, v - (prev[c] ?? 0)]));
    const fut: Record<string, number> = {};
    let net = 0;
    let traded = 0;
    for (const [c, rows] of Object.entries(FUT_HOURS)) {
      const [n, t] = rows[h];
      if (t > 0) {
        fut[c] = Math.round((n / t) * 10000) / 100;
        net -= n;
        traded += t;
      }
    }
    if (traded > 0) fut.USD = Math.round((net / traded) * 10000) / 100;
    return { t: DAY0 + h * HOUR, strength, futures: fut };
  });
  const at = (h: number, m = 0) => DAY0 + h * HOUR + m * 60;
  return {
    from: DAY0, to: DAY0 + 24 * HOUR, now: NOW, hours,
    tracks: [
      { id: 'asia', name: 'Asia', from: at(0), to: at(11), share_pct: 28.1 },
      { id: 'london', name: 'London', from: at(10), to: at(19), share_pct: 37.8 },
      { id: 'new_york', name: 'New York', from: at(15), to: at(24), share_pct: 18.6 },
    ],
  };
}

export function sampleForexBoard(period: Period = '1D'): ForexBoard {
  const moves: Record<string, number> = {};
  for (const [code] of CURRENCIES) {
    const v = vsUsd(code, period);
    if (v != null) moves[code] = v;
  }
  const strength = strengths(moves);
  const rows: Currency[] = CURRENCIES.map(([code, name, city, lat, lon, tz, usd, rank, pair, pairUsd]) => {
    const act = ACTIVITY[code];
    return {
      code, name, city, lat, lon, tz, home: home(tz),
      size: { usd, share_pct: Math.round((usd / BIS_TOTAL) * 10000) / 100, rank, pair, pair_usd: pairUsd },
      price: price(code, period), strength_pct: strength[code] ?? null,
      by_session: code in strength ? { asia: blockChange(code, 0), london: blockChange(code, 1), new_york: blockChange(code, 2) } : null,
      range_x: act ? act[0] : null, volume_x: act ? act[1] : null,
      futures: code === 'USD' ? EMPTY_FUTURES : futures(code, period), mixed: false,
    };
  });
  rows[0].futures = dollarFutures(rows);
  for (const r of rows) {
    const p = r.futures.pressure_pct;
    const s = r.strength_pct;
    r.mixed = p != null && s != null && Math.abs(p) >= 5 && Math.abs(s) >= 0.15 && p > 0 !== s > 0;
  }
  const others = Object.keys(strength).filter((c) => c !== 'USD');
  return {
    schema_version: 1, generated_at: NOW, enabled: true, loading: false, replay_desk: false, period,
    fx_day: { from: DAY0, to: DAY0 + 24 * HOUR, open: true, next_open_at: null },
    market: {
      total_usd: BIS_TOTAL, exchange_traded_usd: 201e9, covered_pct: 95.3,
      instruments: [{ name: 'FX swaps', usd: 4_015.293e9 }, { name: 'Spot', usd: 2_951.766e9 },
        { name: 'Outright forwards', usd: 1_747.311e9 }, { name: 'Options', usd: 631.717e9 }, { name: 'Currency swaps', usd: 164.072e9 }],
      desks: DESKS.map(([name, usd]) => ({ name, usd, share_pct: Math.round((usd / DESKS_TOTAL) * 1000) / 10 })),
      regions: { asia_pacific: 28.1, europe: 49.7, americas: 21.1 },
      as_of: '2025-04', source: 'BIS Triennial Central Bank Survey 2025', url: 'https://www.bis.org/statistics/rpfx25.htm',
    },
    read: readOf(strength, period),
    dollar: {
      strength_pct: strength.USD ?? null, priced: others.length,
      up_against: others.filter((c) => moves[c] < 0).length, down_against: others.filter((c) => moves[c] > 0).length,
      pressure_usd: rows[0].futures.pressure_usd, pressure_pct: rows[0].futures.pressure_pct,
      traded_usd: rows[0].futures.traded_usd, size_usd: 8_472e9, share_pct: 89.08,
    },
    sessions: sessionsOf(), currencies: rows, sun: sunOf(),
    sources: [{ id: 'ibkr', label: 'IBKR', ok: true, at: NOW - 5, error: null }],
    budget: { history_left: 41, history_headroom: 30, waiting: null },
  };
}

/** The majors' pairs from the sample day (for tests). */
export function sampleMajorCross(a: (typeof MAJORS)[number], b: (typeof MAJORS)[number]): number {
  return cross(vsUsd(a, '1D') ?? 0, vsUsd(b, '1D') ?? 0);
}
