/**
 * The demo's backend (ADR 043): every REST route the desk reads, answered in the page with Nova
 * Marketing Sample Data. Nothing here sends anything. A write is refused with the demo's reason,
 * except the venue (Paper or Sim, kept in memory) and the desk's own background reports, which
 * are taken and dropped.
 */
import setupTemplates from '../bot/setupTemplatesFixture.json';
import { sampleCandles } from '../cryptos/sampleCryptos';
import { SAMPLE_SETUPS_SCOREBOARD } from '../sample_data/sampleSetups';
import {
  CLOSED, WORKING, barsFor, captureSessions, catalystsFor, diagnostics, envelope, health, ibkrAccount, ibkrPositions,
  ibkrStatus, practiceAccount, rowFor, tickerDetail, whyFor, type Venue, SMPL,
} from './data/desk';
import { cryptoBoard } from './data/crypto';
import { DAY, NOW_S } from './data/market';
import { botAudit, botSession, practiceHistory, setupRows, setupsBoard, stockModes } from './data/pages';
import { decisions, history, pastSetups, stockMode, stockRead } from './data/read';
import { hodHistory, leaderboardBoard, leaderboardCoverage, leaderboardDays, simClock, simStatus } from './data/sim';
import { CATALYSTS, GAINERS, GAPPERS, HOD_CONFIG, LOSERS, WATCHLIST } from './data/universe';

export interface DemoRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

export interface DemoResponse {
  status: number;
  body: unknown;
}

/** What every refused write says. */
export const DEMO_REFUSAL =
  'This is the live demo: nothing is sent anywhere, so orders and settings do not change. Get Nova from GitHub to trade with your own broker.';

type Handler = (m: RegExpMatchArray, q: URLSearchParams, body: unknown) => unknown;

const ok = (body: unknown): DemoResponse => ({ status: 200, body });
const refuse = (detail: string, status = 403): DemoResponse => ({ status, body: { detail, reason: 'DEMO', error: detail } });
const sym = (m: RegExpMatchArray) => decodeURIComponent(m[1]).toUpperCase();

/** Background reports the desk sends on its own; the demo takes them and keeps nothing. */
const REPORTS = /^\/(?:api\/(?:client-errors|perf\/client|screen-record|clips)|sensors\/focus)$/;

let venue: Venue = 'paper';

/** On Sim the desk takes only candles that say they are the replay's (chart/barsStore.ts). */
const REPLAY_COVERAGE = { replay: true, replay_mode: 'capture', filling: false, as_of: null, complete_through: null, derived_from: 'capture' };

/** The venue the demo desk is on (Paper or Sim). */
export function demoVenue(): Venue {
  return venue;
}

/** Back to Paper (tests). */
export function resetDemoState(): void {
  venue = 'paper';
}

function sharedRoutes(nowS: number): [RegExp, Handler][] {
  return [
    [/^\/api\/health$/, () => ({ ...health(), market_data_source: 'ibkr', data_feed: 'sip', feed_fell_back: false })],
    [/^\/api\/mode$/, () => ({ mode: 'market', health: health(), last_gapper_scan: nowS - 2, last_gainer_scan: nowS - 2 })],
    [/^\/api\/config$/, () => ({
      api_key_set: true, api_secret_set: true, api_key_masked: 'PK****DEMO', api_secret_masked: '****', base_url: 'https://api.alpaca.markets',
      data_feed: 'sip', data_feed_options: ['iex', 'sip'], discovery_provider: 'ibkr', discovery_provider_options: ['ibkr'],
      ibkr_connected: true, scanner_persistent_enabled: true, scanner_persistent_authoritative: false,
    })],
    [/^\/api\/ibkr\/status$/, () => ({ ...ibkrStatus(venue, nowS), ...(venue === 'sim' ? simStatus : {}) })],
    [/^\/api\/ibkr\/feed$/, () => ({
      schema_version: 1, now: nowS, connected: true, in_session: true, last_data_ts: nowS - 0.2, silent_sec: 0.2,
      gap: null, recent: [], rule: { gap_sec: 3, settle_sec: 5, busy_window_sec: 10, busy_fraction: 0.8 },
    })],
    [/^\/api\/ibkr\/gateway-trail$/, () => ({ events: [{ ts: nowS - 20_000, actor: 'nova', event: 'attached', kind_after: 'live', note: 'session ready' }] })],
    [/^\/api\/diagnostics$/, () => diagnostics(nowS)],
    [/^\/api\/gappers$/, () => envelope(nowS, { gappers: GAPPERS })],
    [/^\/api\/movers$/, () => envelope(nowS, { gainers: GAINERS, losers: LOSERS, loser_table_state: 'live', loser_roster_ts: nowS - 2 })],
    [/^\/api\/afterhours$/, () => envelope(nowS, { afterhours: [] })],
    [/^\/api\/large-cap$/, () => envelope(nowS, { large_cap: [] })],
    [/^\/api\/news-catalysts$/, () => envelope(nowS, { catalysts: CATALYSTS, last_scan: nowS - 30 })],
    [/^\/api\/scan\/envelope$/, () => envelope(nowS, { tables: {} })],
    [/^\/api\/history\/dates$/, () => ({ dates: ['2026-09-29', '2026-09-28', '2026-09-25'] })],
    [/^\/api\/halts\/desk$/, () => ({ rev: '4', mwcb: null })],
    [/^\/api\/nova-os\/events$/, () => ({ events: [] })],
    [/^\/api\/integrity$/, () => ({ status: 'pass', ok: true, scope: 'all', checked_at: nowS, checks: [{ id: 'hod_ticks', status: 'pass', detail: 'ticks fresh' }], parts: { hod: 'pass', scanner: 'pass' } })],
    [/^\/api\/hod-momo\/config$/, () => HOD_CONFIG],
    [/^\/api\/hod-momo\/blocklist$/, () => ({ symbols: [] })],
    [/^\/api\/strategy\/watchlist$/, () => ({ note: 'Signal only -- nothing here places an order.', count: WATCHLIST.length, entries: WATCHLIST })],
    [/^\/api\/strategy\/watchlist\/([^/]+)$/, (m) => {
      const i = WATCHLIST.findIndex((e) => e.symbol === sym(m));
      return i < 0 ? undefined : { note: 'Signal only', symbol: WATCHLIST[i].symbol, source: 'gappers', rank: i + 1, entry: WATCHLIST[i] };
    }],
    [/^\/api\/symbols\/directory$/, () => ({
      schema_version: 1, source: 'alpaca_assets', fetched_at: nowS - 3600, count: GAPPERS.length + GAINERS.length, error: null,
      symbols: [...GAPPERS, ...GAINERS, ...LOSERS].map((r) => [r.symbol, r.symbol === 'SMPL' ? 'Sample Pharma Inc.' : `${r.symbol} Sample Co.`, r.exchange]),
    })],
    [/^\/api\/practice\/account$/, () => practiceAccount(venue)],
    [/^\/api\/practice\/history$/, (_m, q) => practiceHistory(q.get('range') ?? '1D', venue)],
    [/^\/api\/ibkr\/account$/, () => ibkrAccount(venue)],
    [/^\/api\/ibkr\/positions$/, () => ibkrPositions(venue)],
    [/^\/api\/ibkr\/orders\/closed$/, () => (venue === 'paper' ? CLOSED : [])],
    [/^\/api\/ibkr\/orders$/, () => (venue === 'paper' ? WORKING : [])],
    [/^\/api\/bot\/session$/, () => botSession(nowS, venue)],
    [/^\/api\/bot\/proposals$/, () => ({ proposals: [] })],
    [/^\/api\/bot\/audit$/, () => ({ entries: botAudit() })],
    [/^\/api\/bot\/pnl$/, () => ({ day_pnl: 450.35, meter: { compares: 'day_pnl', source: 'practice_ledger_day_pnl', venue, compared: true, note: null, error: null, day_pnl: 450.35, commissions: null, commissions_in_figure: true, commissions_unknown: false } })],
    [/^\/api\/kill-switch$/, () => ({ tripped: false, reason: null, ts: null })],
    [/^\/api\/stock-mode$/, () => stockModes(venue)],
    [/^\/api\/stock-mode\/([^/]+)$/, (m) => stockMode(sym(m))],
    [/^\/api\/setups\/templates$/, () => setupTemplates],
    [/^\/api\/setups\/rows$/, () => ({ date: DAY, setup_type: 'all', template: null, rows: setupRows() })],
    [/^\/api\/setups\/scoreboard$/, () => ({ ...SAMPLE_SETUPS_SCOREBOARD, date_from: '2026-09-24' })],
    [/^\/api\/setups\/board$/, () => setupsBoard(nowS)],
    [/^\/api\/chart-drawings\/([^/]+)$/, () => ({ drawings: [] })],
    [/^\/api\/ticker\/([^/]+)\/bars$/, (m, q) => ({ bars: barsFor(sym(m), q.get('timeframe') ?? '1Min', venue), coverage: venue === 'sim' ? REPLAY_COVERAGE : null })],
    [/^\/api\/ticker\/([^/]+)$/, (m) => tickerDetail(sym(m))],
    [/^\/api\/stock-read\/([^/]+)\/history$/, (m) => history(sym(m), SMPL.daily)],
    [/^\/api\/stock-read\/([^/]+)\/past-setups$/, (m, q) => pastSetups(sym(m), q.get('tf'))],
    [/^\/api\/stock-read\/([^/]+)\/decisions$/, (m) => decisions(sym(m))],
    [/^\/api\/stock-read\/([^/]+)\/flush$/, (m) => ({ schema_version: 1, symbol: sym(m), at: nowS, score: 0.41, label: 'burst', window_sec: 30 })],
    [/^\/api\/stock-read\/([^/]+)$/, (m) => stockRead(rowFor(sym(m)), nowS)],
    [/^\/api\/catalysts\/([^/]+)$/, (m) => catalystsFor(sym(m))],
    [/^\/api\/why\/([^/]+)$/, (m) => whyFor(sym(m))],
    [/^\/api\/crypto\/board$/, () => cryptoBoard(nowS)],
    [/^\/api\/crypto\/candles$/, (_m, q) => sampleCandles(q.get('symbol') ?? 'BTC', (q.get('tf') ?? '15m') as Parameters<typeof sampleCandles>[1])],
    [/^\/api\/capture\/sessions$/, () => captureSessions()],
  ];
}

/** Sim's routes: answered only while the desk is on Sim, as the backend only answers them there. */
const SIM_ROUTES: [RegExp, Handler][] = [
  [/^\/api\/sim\/clock$/, () => simClock()],
  [/^\/api\/sim\/history$/, () => ({ jobs: [], selection: null, default_date: '2026-09-29' })],
  // ADR 046: the demo holds no Massive flat files, and says so.
  [/^\/api\/sim\/history\/massive\/days$/, () => ({
    schema_version: 1, available: false, reason: 'The demo holds no Massive files', root: '', days: [],
  })],
  [/^\/api\/leaderboard\/days$/, () => leaderboardDays()],
  [/^\/api\/leaderboard\/([0-9-]+)\/coverage$/, (m) => leaderboardCoverage(m[1])],
  [/^\/api\/leaderboard\/([0-9-]+)\/halts$/, (m) => ({ date: m[1], events: [] })],
  [/^\/api\/leaderboard\/([0-9-]+)$/, (m) => leaderboardBoard(m[1])],
  [/^\/api\/hod-momo\/history\/([0-9-]+)$/, () => hodHistory()],
];

function venueChange(body: unknown): DemoResponse {
  const want = (body as { venue?: unknown } | null)?.venue;
  if (want === 'paper' || want === 'sim') {
    venue = want;
    return ok({ ok: true, venue, left: [] });
  }
  return refuse('The demo has no broker, so Live is off. Paper and Sim run on Nova Marketing Sample Data.', 409);
}

/** Answer one request; `undefined` means "not a route the demo knows" (the transport says 404). */
export function answer(req: DemoRequest, nowS = Date.now() / 1000): DemoResponse | undefined {
  const method = req.method.toUpperCase();
  if (method !== 'GET' && method !== 'HEAD') {
    if (REPORTS.test(req.path)) return ok({ ok: true });
    if (method === 'POST' && req.path === '/api/desk/venue') return venueChange(req.body);
    return refuse(DEMO_REFUSAL);
  }
  const routes = venue === 'sim' ? [...SIM_ROUTES, ...sharedRoutes(nowS)] : sharedRoutes(nowS);
  for (const [re, fn] of routes) {
    const m = req.path.match(re);
    if (!m) continue;
    const body = fn(m, req.query, req.body);
    return body === undefined ? undefined : ok(body);
  }
  return undefined;
}

/** The sample morning's "now" in seconds (where the demo clock starts). */
export const DEMO_START_S = NOW_S;
