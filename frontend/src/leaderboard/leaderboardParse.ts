/**
 * Boundary parsers for the leaderboard routes. A body that is not an object
 * throws (read as a failed request); a damaged field reads as unknown (null)
 * and a damaged row is skipped -- never a placeholder number.
 */
import { finiteOrNull, isObject, objects, text, textOrNull, type Obj } from '../sim/payloadGuards';
import type {
  LeaderboardAt,
  LeaderboardBoard,
  LeaderboardCoverage,
  LeaderboardDay,
  LeaderboardDays,
  LeaderboardDaySummary,
  LeaderboardGap,
  LeaderboardRow,
  LeaderboardSource,
} from './leaderboardTypes';

const unreadable = (what: string): string => `Nova returned an unreadable ${what}.`;

const boolOrNull = (value: unknown): boolean | null => (typeof value === 'boolean' ? value : null);

function source(value: unknown): LeaderboardSource | null {
  return value === 'recorded' || value === 'reconstructed' ? value : null;
}

export function parseLeaderboardRow(raw: Obj, board: string): LeaderboardRow | null {
  const symbol = text(raw.symbol)?.trim().toUpperCase();
  if (!symbol) return null;
  const basis = raw.rvol_basis === 'daily_avg' || raw.rvol_basis === 'time_of_day_20' ? raw.rvol_basis : null;
  return {
    symbol,
    minute_ts: finiteOrNull(raw.minute_ts),
    board: text(raw.board) ?? board,
    source: textOrNull(raw.source),
    rank: finiteOrNull(raw.rank),
    price: finiteOrNull(raw.price),
    prev_close: finiteOrNull(raw.prev_close),
    change_pct: finiteOrNull(raw.change_pct),
    volume: finiteOrNull(raw.volume),
    rvol: finiteOrNull(raw.rvol),
    rvol_basis: basis,
    float_shares: finiteOrNull(raw.float_shares),
    has_news: boolOrNull(raw.has_news),
    news_first_seen_ts: finiteOrNull(raw.news_first_seen_ts),
    halted: boolOrNull(raw.halted),
    gap_pct: finiteOrNull(raw.gap_pct),
    exchange: textOrNull(raw.exchange),
    market_cap: finiteOrNull(raw.market_cap),
  };
}

function parseGap(value: unknown): LeaderboardGap | null {
  if (!isObject(value)) return null;
  return {
    reason: text(value.reason) ?? 'unknown',
    start: finiteOrNull(value.start),
    end: finiteOrNull(value.end),
    stop: textOrNull(value.stop),
  };
}

function parseBoards(value: unknown): Record<string, LeaderboardBoard> {
  const out: Record<string, LeaderboardBoard> = {};
  if (!isObject(value)) return out;
  for (const [name, board] of Object.entries(value)) {
    if (!isObject(board)) continue;
    out[name] = {
      state: textOrNull(board.state),
      rows: objects(board.rows)
        .map(row => parseLeaderboardRow(row, name))
        .filter((row): row is LeaderboardRow => row != null),
    };
  }
  return out;
}

/** `GET /api/leaderboard/{date}?at=` */
export function parseLeaderboardAt(raw: unknown): LeaderboardAt {
  if (!isObject(raw)) throw new Error(unreadable('Scanner board'));
  const leaders = isObject(raw.leaders) && Array.isArray(raw.leaders.symbols)
    ? raw.leaders.symbols.filter((s): s is string => typeof s === 'string')
    : [];
  const gap = parseGap(raw.gap);
  return {
    date: text(raw.date) ?? '',
    at: finiteOrNull(raw.at),
    source: source(raw.source),
    minute_ts: finiteOrNull(raw.minute_ts),
    // A board answer with a gap is never "covered", whatever the flag says.
    covered: raw.covered === true && gap == null,
    gap,
    boards: gap ? {} : parseBoards(raw.boards),
    leaders,
  };
}

function summary(value: unknown): LeaderboardDaySummary | null {
  if (!isObject(value)) return null;
  return {
    minutes: finiteOrNull(value.minutes),
    first_ts: finiteOrNull(value.first_ts),
    last_ts: finiteOrNull(value.last_ts),
  };
}

/** `GET /api/leaderboard/days` */
export function parseLeaderboardDays(raw: unknown): LeaderboardDays {
  if (!isObject(raw)) throw new Error(unreadable('Scanner board day list'));
  const store = isObject(raw.store) ? raw.store : {};
  const days = objects(raw.days)
    .map((day): LeaderboardDay | null => {
      const date = text(day.date);
      if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
      return { date, recorded: summary(day.recorded), reconstructed: summary(day.reconstructed) };
    })
    .filter((day): day is LeaderboardDay => day != null && (day.recorded != null || day.reconstructed != null));
  return {
    store: { path: textOrNull(store.path), ok: store.ok !== false, error: textOrNull(store.error) },
    days,
  };
}

const isSpan = (pair: unknown): pair is number[] => Array.isArray(pair) && pair.length >= 2
  && Number.isFinite(pair[0]) && Number.isFinite(pair[1]) && pair[1] > pair[0];

/** `GET /api/leaderboard/{date}/coverage` */
export function parseLeaderboardCoverage(raw: unknown): LeaderboardCoverage {
  if (!isObject(raw)) throw new Error(unreadable('Scanner board coverage'));
  return {
    date: text(raw.date) ?? '',
    source: source(raw.source),
    session_open: finiteOrNull(raw.session_open),
    session_close: finiteOrNull(raw.session_close),
    spans: (Array.isArray(raw.spans) ? raw.spans : []).filter(isSpan).map(([a, b]) => [a, b]),
    gaps: objects(raw.gaps)
      .map(gap => ({ start: finiteOrNull(gap.start), end: finiteOrNull(gap.end), reason: text(gap.reason) ?? 'unknown' }))
      .filter((gap): gap is { start: number; end: number; reason: string } =>
        gap.start != null && gap.end != null && gap.end > gap.start),
  };
}
