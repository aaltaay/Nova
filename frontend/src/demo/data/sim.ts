/**
 * The Sim venue in the demo (ADR 043): yesterday's Session Record of RUNR loaded, the playhead
 * at 09:52:40 ET, yesterday's board at the playhead and the recorded stretches on the scrubber.
 * Nova Marketing Sample Data.
 */
import { etMs } from './market';
import { GAINERS, GAPPERS, HOD_ALERTS, type ScannerRow } from './universe';

export const SIM_DAY = '2026-09-29';
const at = (h: number, m: number, s = 0) => etMs(h, m, s, SIM_DAY) / 1000;
const OPEN = at(4, 0);
const CLOSE = at(20, 0);
const PLAYHEAD = at(9, 52, 40);
/** The loaded Session Record: RUNR at the playhead. */
export const SIM_SYMBOL = 'RUNR';
export const SIM_LAST = 5.12;
export const SIM_PREV_CLOSE = 3.9;
export const SIM_PLAYHEAD_MS = PLAYHEAD * 1000;
const DAY_S = 86_400;

const SEGMENTS = [
  { started_et: '2026-09-29T07:02:11-04:00', stopped_et: '2026-09-29T09:58:40-04:00', status: 'stopped_partial_ok', reason: 'restart' },
  { started_et: '2026-09-29T09:59:22-04:00', stopped_et: '2026-09-29T11:30:05-04:00', status: 'stopped_partial_ok', reason: 'operator' },
];

export function simClock() {
  return {
    sim: true, sim_time_et: '2026-09-29T09:52:40-04:00', session_date: SIM_DAY, phase: 'rth',
    session_open_et: '2026-09-29T04:00:00-04:00', session_close_et: '2026-09-29T20:00:00-04:00',
    minute_from_open: 352, second_from_open: 21160, minute_max: 960, second_max: 57600,
    scrubbed: true, paused: true, live_edge: false, replay_date: SIM_DAY, replay_symbol: 'RUNR', replay_source: 'capture',
    replay_ok: true, replay_loading: false, replay_error: null,
    replay_quote: { symbol: SIM_SYMBOL, ts: PLAYHEAD, covered: true, last: SIM_LAST, bid: 5.11, ask: SIM_LAST, bid_size: 1200, ask_size: 800, prev_close: SIM_PREV_CLOSE },
    replay_load: { l2_total: 120_554, l2_loaded: 120_554, l2_decimated: false, malformed_rows: 0, invalid_timestamp_rows: 0, invalid_rows: 0, legacy_schema: false, segments: SEGMENTS },
  };
}

export const simStatus = { mode: 'sim', venue: 'sim', sim: true, live_edge: false, account_id: 'NOVA-SIM', account_ids: ['NOVA-SIM'] };

export function leaderboardDays() {
  return {
    schema_version: 1, store: { path: 'leaderboard.sqlite3', ok: true, error: null },
    days: [
      { date: '2026-09-30', recorded: { minutes: 341, first_ts: OPEN + DAY_S, last_ts: at(9, 41) + DAY_S, boards: ['gappers', 'gainers', 'losers'] }, reconstructed: null },
      { date: SIM_DAY, recorded: { minutes: 960, first_ts: OPEN, last_ts: CLOSE, boards: ['gappers', 'gainers', 'losers'] }, reconstructed: { minutes: 960, first_ts: OPEN, last_ts: CLOSE } },
      { date: '2026-09-28', recorded: { minutes: 960, first_ts: OPEN - DAY_S, last_ts: CLOSE - DAY_S, boards: ['gappers'] }, reconstructed: null },
    ],
  };
}

export const leaderboardCoverage = (date: string) => ({ date, source: 'recorded', session_open: OPEN, session_close: CLOSE, spans: [[OPEN, CLOSE]], gaps: [] });

function lbRow(r: ScannerRow, board: string, rank: number) {
  const seen = r.catalyst ? r.catalyst.published_ts - DAY_S : null;
  return {
    symbol: r.symbol, minute_ts: at(9, 52), board, source: 'recorded', rank,
    price: r.price, prev_close: r.prev_close, change_pct: r.change_pct, volume: r.volume, rvol: r.rel_volume,
    rvol_basis: 'daily_avg', float_shares: r.float, float_contradicted: false, shares_outstanding: r.shares_outstanding,
    has_news: r.has_news, news_first_seen_ts: seen, halted: false, gap_pct: r.gap_percent, exchange: r.exchange,
    market_cap: r.market_cap, catalyst: r.catalyst && seen != null ? { ...r.catalyst, published_ts: seen } : null,
  };
}

export function leaderboardBoard(date: string) {
  return {
    schema_version: 1, date, at: PLAYHEAD, source: 'recorded', minute_ts: at(9, 52), covered: true, gap: null,
    boards: {
      gappers: { state: 'live', rows: GAPPERS.map((r, i) => lbRow(r, 'gappers', i + 1)) },
      gainers: { state: 'live', rows: GAINERS.map((r, i) => lbRow(r, 'gainers', i + 1)) },
    },
    leaders: { board: 'gainers', symbols: ['RUNR', 'SMPL', 'GAPX'], rules: {} },
    catalyst_symbols: 6,
  };
}

/** Yesterday's alert history, a day and a few minutes earlier than today's. */
export function hodHistory() {
  return HOD_ALERTS.map((a) => {
    const ts = a.created_ts - DAY_S + 680;
    return { ...a, created_ts: ts, timestamp: new Date(ts * 1000).toISOString() };
  });
}
