/**
 * The Congress page on the sample desk (ADR 066): Nova Marketing Sample Data -- invented members ("Senator 12"),
 * invented trades, initials instead of photos. Nothing here is a real report or a real member; the page says so.
 * Deterministic (a seeded generator), so the sample desk draws the same page every time.
 */
import type {
  Active, Board, Member, MemberAnswer, MemberStats, MembersAnswer, Period, ReportRow, TickerAnswer, Trade, Traded,
} from './types';

const STATES = ['AL', 'AK', 'AZ', 'CA', 'CO', 'FL', 'GA', 'IL', 'MI', 'NC', 'NY', 'OH', 'PA', 'TX', 'VA', 'WA'];
const TICKERS: [string, string][] = [
  ['AAPL', 'Apple Inc.'], ['MSFT', 'Microsoft Corporation'], ['NVDA', 'NVIDIA Corporation'], ['AMZN', 'Amazon.com, Inc.'],
  ['META', 'Meta Platforms, Inc.'], ['HD', 'The Home Depot, Inc.'], ['PG', 'The Procter & Gamble Company'],
  ['ACN', 'Accenture plc'],
];
const TODAY = '2026-10-14';
const YEAR = 2026;

function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function bio(prefix: string, n: number): string {
  return `${prefix}${String(n).padStart(6, '0')}`;
}

function members(): { senate: Member[]; house: Member[] } {
  const senate: Member[] = [];
  const house: Member[] = [];
  const party = (i: number, d: number, ind: number) => (i < d ? 'D' : i < d + ind ? 'I' : 'R');
  for (let i = 0; i < 100; i += 1) {
    senate.push({ bioguide: bio('S', i + 1), name: `Senator ${i + 1}`, party: party(i, 45, 2), caucus: null,
      state: STATES[i % STATES.length], district: null, chamber: 'senate', current: true, left: null, photo: false });
  }
  for (let i = 0; i < 433; i += 1) {
    house.push({ bioguide: bio('H', i + 1), name: `Representative ${i + 1}`, party: party(i, 214, 1), caucus: null,
      state: STATES[i % STATES.length], district: (i % 12) + 1, chamber: 'house', current: true, left: null,
      photo: false });
  }
  return { senate, house };
}

const SEATED = members();
const ALL = [...SEATED.senate, ...SEATED.house];
const BY_BIO = new Map(ALL.map((m) => [m.bioguide, m]));

function pick<T>(r: () => number, items: T[], n: number): T[] {
  const copy = [...items];
  const out: T[] = [];
  while (out.length < n && copy.length) out.push(copy.splice(Math.floor(r() * copy.length), 1)[0]);
  return out;
}

function reporters(): Record<Period, Record<string, 'trades' | 'paper'>> {
  const r = rng(66);
  const ytd: Record<string, 'trades' | 'paper'> = {};
  for (const m of pick(r, SEATED.senate, 28)) ytd[m.bioguide] = 'trades';
  for (const m of pick(r, SEATED.house, 98)) ytd[m.bioguide] = 'trades';
  for (const m of pick(r, SEATED.house.filter((x) => !ytd[x.bioguide]), 10)) ytd[m.bioguide] = 'paper';
  const keys = Object.keys(ytd);
  const sub = (n: number) => Object.fromEntries(keys.slice(0, n).map((k) => [k, ytd[k]]));
  return { ytd, '90d': sub(70), '30d': sub(34) };
}

const REPORTED = reporters();
const TRADERS = Object.keys(REPORTED.ytd).filter((k) => REPORTED.ytd[k] === 'trades');

function traded(): Traded[] {
  const r = rng(7);
  return TICKERS.map(([ticker, asset], i) => {
    const buyers = pick(r, TRADERS, 12 - i).map(String);
    const sellers = pick(r, TRADERS.filter((t) => !buyers.includes(t)), 14 - i).map(String);
    return { ticker, asset, members: buyers.length + sellers.length, buyers, sellers, buys: buyers.length + 2,
      sells: sellers.length + 1 };
  });
}

function trade(i: number, m: Member, side: 'buy' | 'sell', t: [string, string], filed: string, tx: string): Trade {
  const lag = Math.round((Date.parse(filed) - Date.parse(tx)) / 86_400_000);
  return { id: `SAMPLE:${i}#0`, report: `SAMPLE:${i}`, chamber: m.chamber, bioguide: m.bioguide, filer: m.name, filed,
    tx, notified: tx, lag_days: lag, late: lag > 45, owner: i % 3 === 0 ? 'spouse' : 'self', ticker: t[0],
    asset: t[1], asset_type: m.chamber === 'house' ? 'ST' : 'Stock', kind: 'stock', side, partial: false, gift: false,
    amount: { text: '$1,001 - $15,000', low: 1001, high: 15000 }, description: '', status: 'new',
    url: 'https://example.invalid/sample-report', member: m };
}

function sampleTrades(): Trade[] {
  const r = rng(11);
  const out: Trade[] = [];
  for (let i = 0; i < 40; i += 1) {
    const m = BY_BIO.get(TRADERS[i % TRADERS.length]) as Member;
    const d = 12 - Math.floor(i / 4);
    const filed = `2026-10-${String(Math.max(1, d)).padStart(2, '0')}`;
    const tx = `2026-09-${String(1 + Math.floor(r() * 28)).padStart(2, '0')}`;
    out.push(trade(i, m, r() < 0.55 ? 'buy' : 'sell', TICKERS[Math.floor(r() * TICKERS.length)], filed, tx));
  }
  return out;
}

const TRADES = sampleTrades();

function weeks(seed: number) {
  const r = rng(seed);
  return { from: '2026-04-15', buy: Array.from({ length: 26 }, () => Math.floor(r() * r() * 9)),
    sell: Array.from({ length: 26 }, () => Math.floor(r() * r() * 7)) };
}

function active(): Active[] {
  return TRADERS.slice(0, 5).map((b, i) => ({ ...(BY_BIO.get(b) as Member), trades: 240 - i * 45, buys: 130 - i * 20,
    sells: 110 - i * 25, median_lag_days: [23, 15, 19, 28, 61][i], late: [0, 0, 2, 1, 40][i], weeks: weeks(i + 3),
    top: TICKERS.slice(i, i + 3).map(([t]) => t) }));
}

function justReported(): ReportRow[] {
  const rows: ReportRow[] = TRADES.slice(0, 8).map((t, i) => ({ id: t.report, chamber: t.chamber, member: t.member ?? null,
    filer: t.filer, filed: t.filed, kind: 'electronic', read: true, url: t.url, amends: null, trades: 1 + (i * 7) % 40,
    top: { ticker: t.ticker, asset: t.asset, side: t.side, kind: t.kind, gift: false, amount: t.amount.text,
      lag_days: t.lag_days } }));
  const paper = SEATED.house.find((m) => REPORTED.ytd[m.bioguide] === 'paper') as Member;
  rows.push({ id: 'SAMPLE:paper', chamber: 'house', member: paper, filer: paper.name, filed: '2026-10-07', kind: 'paper',
    read: false, url: 'https://example.invalid/sample-paper', amends: null, trades: 0, top: null });
  return rows;
}

export function sampleCongressBoard(): Board {
  const t = traded();
  return {
    schema_version: 1, generated_at: Date.parse(`${TODAY}T23:30:00-04:00`) / 1000, enabled: true, today: TODAY,
    year: YEAR, consent: { state: 'given', accepted_at: null, text: '', cite: '' },
    sources: (['house', 'senate', 'roster', 'photos'] as const).map((id) => ({ id, name: id, url: '', state: 'ok',
      read_at: Date.parse(`${TODAY}T23:30:00-04:00`) / 1000, next_at: null, error: null, done: 0, todo: 0 })),
    counts: { all: 5126, house: 3486, senate: 1640, buys: 2787, sells: 2292, options: 57, late: 1178 },
    periods: { ytd: { from: '2026-01-01' }, '90d': { from: '2026-07-16' }, '30d': { from: '2026-09-14' } },
    seats: { senate: SEATED.senate, house: SEATED.house, delegates: [], former: [], empty: { senate: 0, house: 2 } },
    reported: REPORTED, just_reported: justReported(),
    most_traded: { ytd: t, '90d': t.slice(0, 6), '30d': t.slice(0, 4) },
    most_active: active(),
    lag: { bucket_days: 5, limit_days: 45, trades: 5126, median_days: 28, within_week_pct: 5.9, after_limit_pct: 24.1,
      buckets: [120, 210, 380, 520, 610, 690, 540, 210, 160, 80, 60, 45, 30, 25, 20, 18, 15, 12, 10, 9, 8, 7, 6, 5, 700] },
  };
}

function stats(m: Member, i: number): MemberStats {
  const n = TRADERS.includes(m.bioguide) ? 40 - (i % 40) : 0;
  return { ...m, committees: [], ytd: { trades: n, buys: Math.ceil(n / 2), sells: Math.floor(n / 2), reports: n ? 3 : 0,
    paper: REPORTED.ytd[m.bioguide] === 'paper' ? 1 : 0 }, last_filed: n ? '2026-10-07' : null,
    median_lag_days: n ? 20 + (i % 15) : null, late: 0 };
}

export function sampleCongressMembers(): MembersAnswer {
  const all = ALL.map(stats).sort((a, b) => b.ytd.trades - a.ytd.trades || a.name.localeCompare(b.name));
  return { schema_version: 1, generated_at: 0, year: YEAR, members: all };
}

export function sampleCongressMember(bioguide: string): MemberAnswer | null {
  const m = BY_BIO.get(bioguide);
  if (!m) return null;
  const mine = TRADES.filter((t) => t.bioguide === bioguide);
  return { schema_version: 1, generated_at: 0, member: stats(m, 0), weeks: weeks(bioguide.length), trades: mine,
    reports: mine.map((t) => ({ id: t.report, chamber: t.chamber, filed: t.filed, kind: 'electronic', read: true,
      error: null, url: t.url, amends: null, amended_by: null, trades: 1 })) };
}

export function sampleCongressTicker(ticker: string): TickerAnswer {
  const mine = TRADES.filter((t) => t.ticker === ticker);
  return { schema_version: 1, generated_at: 0, ticker, asset: mine[0]?.asset ?? null,
    buyers: [...new Set(mine.filter((t) => t.side === 'buy').map((t) => t.bioguide as string))],
    sellers: [...new Set(mine.filter((t) => t.side === 'sell').map((t) => t.bioguide as string))], trades: mine };
}
