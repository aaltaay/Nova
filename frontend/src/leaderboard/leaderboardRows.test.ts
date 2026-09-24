/** @vitest-environment jsdom */
import { describe, expect, it } from 'vitest';
import { SCANNER_RVOL_SOURCE_MARKS } from '../constantGroups/scanner_board';
import { chipPasses } from '../scanner/boardFilters';
import { historyDatesUrl } from '../scanner/scannerHistory';
import { parseLeaderboardAt, parseLeaderboardCoverage, parseLeaderboardDays } from './leaderboardParse';
import {
  gapText, replayFromAnswer, replayLabel, replayListAbsence, replayNotice, replayPending, scannerRowFromLeaderboard,
} from './leaderboardRows';
import { LEADERBOARD_CATALYSTS_IN_NEWS_COLUMN, LEADERBOARD_CATALYSTS_NOT_RECORDED } from './leaderboardConstants';
import type { LeaderboardRow } from './leaderboardTypes';

/** 2026-09-21 07:42:00 ET (EDT, UTC-4). */
const M0742 = Date.parse('2026-09-21T07:42:00-04:00') / 1000;
const at = (hhmm: string) => Date.parse(`2026-09-21T${hhmm}:00-04:00`) / 1000;

const row = (over: Partial<LeaderboardRow> = {}): LeaderboardRow => ({
  symbol: 'GRML', minute_ts: M0742, board: 'gainers', source: 'recorded', rank: 1,
  price: 9.27, prev_close: 5.0, change_pct: 0.854, volume: 4_820_000, rvol: 12.5, rvol_basis: 'daily_avg',
  float_shares: 8_200_000, has_news: true, news_first_seen_ts: M0742 - 600, halted: false,
  gap_pct: 0.4, exchange: 'NASDAQ', market_cap: 45_000_000, catalyst: null, ...over,
});

/** A verdict as `GET /api/leaderboard/{date}` carries it (catalysts.live.WIRE_KEYS). */
const WIRE_VERDICT = {
  verdict: 'catalyst', category: 'fda_regulatory', strength: 'strong',
  title: 'Acme Receives FDA Approval for Its Lead Drug', source: 'alpaca', published_ts: M0742 - 300,
  url: 'https://example.test/fda', negative_too: false, rules_version: 'catalyst-rules-v6-2026-09-23',
  sources_answered: ['alpaca', 'edgar'], n_items: 2, news_pending: false, halt_code: null,
};

const answer = (over: Record<string, unknown> = {}) => parseLeaderboardAt({
  schema_version: 1, date: '2026-09-21', at: M0742 + 10, source: 'recorded', minute_ts: M0742, covered: true, gap: null,
  boards: {
    gainers: { state: 'live', rows: [row({ symbol: 'B', rank: 2 }), row({ symbol: 'A', rank: 1 })] },
    gappers: { state: 'frozen', rows: [] },
    afterhours: { state: 'unavailable', rows: [] },
  },
  leaders: { board: 'gainers', symbols: ['A'], rules: {} },
  ...over,
});

describe('leaderboard row -> Scanner row', () => {
  it('maps field by field and derives only change_abs', () => {
    const out = scannerRowFromLeaderboard(row());
    expect(out).toMatchObject({
      symbol: 'GRML', price: 9.27, prev_close: 5.0, change_pct: 0.854, gap_percent: 0.4, volume: 4_820_000,
      rel_volume: 12.5, rvol_source: 'daily_avg', float: 8_200_000, market_cap: 45_000_000, exchange: 'NASDAQ',
      rank: 1, has_news: true, news_unknown: false, halted: false, newest_headline_at: null,
    });
    expect(out.change_abs).toBeCloseTo(4.27);
  });

  it('keeps every unknown null -- never 0 -- and says an unknown news fact is unknown', () => {
    const out = scannerRowFromLeaderboard(row({
      price: null, change_pct: null, volume: null, rvol: null, rvol_basis: null, float_shares: null,
      has_news: null, halted: null, gap_pct: null, market_cap: null,
    }));
    expect(out.price).toBeNull();
    expect(out.change_abs).toBeNull();
    expect(out.change_pct).toBeNull();
    expect(out.volume).toBeNull();
    expect(out.rel_volume).toBeNull();
    expect(out.rvol_source).toBeNull();
    expect(out.float).toBeNull();
    expect(out.gap_percent).toBeNull();
    expect(out.halted).toBeNull();
    expect(out.has_news).toBe(false);
    expect(out.news_unknown).toBe(true);
  });

  it('names the RVOL basis with its own mark, so two bases are never read alike', () => {
    const tod = scannerRowFromLeaderboard(row({ rvol_basis: 'time_of_day_20' }));
    expect(tod.rvol_source).toBe('time_of_day_20');
    expect(SCANNER_RVOL_SOURCE_MARKS.time_of_day_20.title).toMatch(/time-of-day RVOL \(20 sessions\)/i);
    expect(SCANNER_RVOL_SOURCE_MARKS.daily_avg.title).toMatch(/average daily volume/);
  });

  it('parses each row\'s verdict at the playhead; an absent or damaged one is unknown', () => {
    const parsed = parseLeaderboardAt({
      date: '2026-09-21', at: M0742 + 10, source: 'recorded', minute_ts: M0742, covered: true, gap: null,
      catalyst_symbols: 3,
      boards: { gainers: { state: 'live', rows: [
        { symbol: 'ACME', catalyst: WIRE_VERDICT },
        { symbol: 'NONE', catalyst: null },
        { symbol: 'OLD' },
        { symbol: 'BAD', catalyst: { verdict: 'maybe' } },
      ] } },
    });
    const [acme, none, old, bad] = parsed.boards.gainers.rows;
    expect(parsed.catalyst_symbols).toBe(3);
    expect(acme.catalyst).toMatchObject({
      verdict: 'catalyst', category: 'fda_regulatory', strength: 'strong', title: WIRE_VERDICT.title,
      published_ts: M0742 - 300, sources_answered: ['alpaca', 'edgar'], n_items: 2, news_pending: false,
    });
    expect([none.catalyst, old.catalyst, bad.catalyst]).toEqual([null, null, null]);
  });

  it('carries a verdict on file, aged from the playhead; none on file leaves the row without one', () => {
    const replay = replayFromAnswer('2026-09-21', M0742, answer({
      boards: { gainers: { state: 'live', rows: [
        row({ symbol: 'ACME', rank: 1, catalyst: WIRE_VERDICT as LeaderboardRow['catalyst'] }),
        row({ symbol: 'NONE', rank: 2, catalyst: null }),
      ] } },
    }));
    const [acme, none] = replay.tables.gainers;
    expect(acme.catalyst?.verdict).toBe('catalyst');
    expect(acme.catalyst_as_of).toBe(M0742 + 10);
    expect('catalyst' in none).toBe(false);
    expect(none.catalyst_as_of).toBeUndefined();
    expect(chipPasses('news', acme)).toBe(true);
  });

  it('a damaged field reads as unknown and a row without a symbol is skipped', () => {
    const parsed = parseLeaderboardAt({
      date: '2026-09-21', source: 'recorded', minute_ts: M0742, covered: true, gap: null,
      boards: { gainers: { state: 'live', rows: [{ symbol: 'X', price: '9.1', volume: Number.NaN }, { price: 3 }] } },
    });
    expect(parsed.boards.gainers.rows).toHaveLength(1);
    expect(parsed.boards.gainers.rows[0].price).toBeNull();
    expect(parsed.boards.gainers.rows[0].volume).toBeNull();
  });
});

describe('the played-back board', () => {
  it('fills the recorded lists in rank order and labels them recorded', () => {
    const replay = replayFromAnswer('2026-09-21', M0742, answer());
    expect(replay.tables.gainers.map(r => r.symbol)).toEqual(['A', 'B']);
    expect(replayLabel(replay)).toBe('Sim · 2026-09-21 07:42 ET · recorded');
    expect(replayNotice(replay)).toBeNull();
    expect(replay.leaders).toEqual(['A']);
  });

  it('a rebuilt day shows its one market board under Gainers and states the rest', () => {
    const replay = replayFromAnswer('2026-09-18', M0742, answer({
      source: 'reconstructed', boards: { market: { state: 'rebuilt', rows: [row({ symbol: 'MKT', board: 'market' })] } },
    }));
    expect(replay.tables.gainers.map(r => r.symbol)).toEqual(['MKT']);
    expect(replay.tables.gappers).toEqual([]);
    expect(replayLabel(replay)).toBe('Sim · 2026-09-18 07:42 ET · rebuilt');
    expect(replayListAbsence(replay, 'gappers')).toMatch(/^Not rebuilt for this day/);
  });

  it('a gap is a stated absence with its reason and times, and no rows', () => {
    const replay = replayFromAnswer('2026-09-21', M0742, answer({
      covered: false, gap: { reason: 'not_running', start: at('09:12'), end: at('09:31'), stop: null },
    }));
    expect(replay.tables.gainers).toEqual([]);
    expect(replayNotice(replay)).toBe('No board: Nova not running 09:12-09:31');
    expect(replayListAbsence(replay, 'gainers')).toBe('No board: Nova not running 09:12-09:31');
    expect(replayLabel(replay)).toBe('Sim · 2026-09-21 07:42 ET');
  });

  it('every gap reason reads in words', () => {
    expect(gapText({ reason: 'feed_down', start: at('10:01'), end: at('10:04'), stop: null }))
      .toBe('No board: IBKR feed down 10:01-10:04');
    expect(gapText({ reason: 'not_running', start: at('09:12'), end: at('09:31'), stop: 'unexpected' }))
      .toBe('No board: Nova not running 09:12-09:31 (Nova stopped unexpectedly)');
    expect(gapText({ reason: 'not_recorded', start: at('04:00'), end: at('20:01'), stop: null }))
      .toBe('No board recorded for this day');
    expect(gapText({ reason: 'outside_session', start: null, end: null, stop: null }))
      .toBe('Outside the 04:00-20:00 session');
  });

  it('a list the minute did not record, or recorded as unavailable, says so', () => {
    const replay = replayFromAnswer('2026-09-21', M0742, answer());
    expect(replayListAbsence(replay, 'losers')).toBe('No losers list recorded at 07:42 ET');
    expect(replayListAbsence(replay, 'afterhours')).toBe('The after-hours movers list was unavailable at 07:42 ET');
    expect(replayListAbsence(replay, 'gappers')).toBe('No gappers on the board at 07:42 ET');
    expect(replayListAbsence(replay, 'catalysts')).toBe(LEADERBOARD_CATALYSTS_NOT_RECORDED);
  });

  it('the Catalysts tab points at the News column only when the day has catalysts on file', () => {
    const onFile = replayFromAnswer('2026-09-21', M0742, answer({ catalyst_symbols: 14 }));
    expect(onFile.catalystSymbols).toBe(14);
    expect(replayListAbsence(onFile, 'catalysts')).toBe(LEADERBOARD_CATALYSTS_IN_NEWS_COLUMN);
    const none = replayFromAnswer('2026-09-21', M0742, answer({ catalyst_symbols: 0 }));
    expect(replayListAbsence(none, 'catalysts')).toBe(LEADERBOARD_CATALYSTS_NOT_RECORDED);
    const older = replayFromAnswer('2026-09-21', M0742, answer());   // an API from before #498
    expect(older.catalystSymbols).toBeNull();
    expect(replayListAbsence(older, 'catalysts')).toBe(LEADERBOARD_CATALYSTS_NOT_RECORDED);
    expect(replayPending('2026-09-21', M0742).catalystSymbols).toBeNull();
  });

  it('loading and failure are stated, never a quiet market', () => {
    expect(replayListAbsence(replayPending('2026-09-21', M0742), 'gainers')).toBe('Loading the board at 07:42 ET…');
    const failed = replayPending('2026-09-21', M0742, 'Nova did not respond in time.');
    expect(replayListAbsence(failed, 'gainers')).toBe('Could not load the board at 07:42 ET: Nova did not respond in time.');
    expect(replayLabel(replayPending('2026-09-21', M0742))).toBe('Sim · 2026-09-21 07:42 ET · loading');
  });
});

describe('leaderboard listings', () => {
  it('days keep only real dates with a board, and a broken store is stated', () => {
    const days = parseLeaderboardDays({
      store: { path: 'F:/Nova/leaderboard', ok: false, error: 'disk full' },
      days: [
        { date: '2026-09-21', recorded: { minutes: 200, first_ts: 1, last_ts: 2, boards: ['gainers'] }, reconstructed: null },
        { date: '2026-09-18', recorded: null, reconstructed: { minutes: 960, first_ts: 1, last_ts: 2 } },
        { date: 'nope', recorded: {} },
        { date: '2026-09-17', recorded: null, reconstructed: null },
      ],
    });
    expect(days.days.map(d => d.date)).toEqual(['2026-09-21', '2026-09-18']);
    expect(days.store).toEqual({ path: 'F:/Nova/leaderboard', ok: false, error: 'disk full' });
  });

  it('coverage keeps well-formed spans and gaps only', () => {
    const coverage = parseLeaderboardCoverage({
      date: '2026-09-21', source: 'recorded', session_open: 1, session_close: 2,
      spans: [[10, 20], [30, 25], null, [40, 'x']],
      gaps: [{ start: 20, end: 30, reason: 'not_running' }, { start: 5, end: null, reason: 'feed_down' }],
    });
    expect(coverage.spans).toEqual([[10, 20]]);
    expect(coverage.gaps).toEqual([{ start: 20, end: 30, reason: 'not_running' }]);
  });

  it('the past-day menu asks for every date with any saved board (type=all)', () => {
    expect(historyDatesUrl('http://x/api')).toBe('http://x/api/history/dates?type=all');
  });
});

describe('board chips on played-back rows fail open on unknowns', () => {
  it('an unrecorded news fact and a time-of-day RVOL pass their chips', () => {
    const unknownNews = scannerRowFromLeaderboard(row({ has_news: null }));
    expect(chipPasses('news', unknownNews)).toBe(true);
    expect(chipPasses('news', scannerRowFromLeaderboard(row({ has_news: false })))).toBe(false);
    const tod = scannerRowFromLeaderboard(row({ rvol: 1.2, rvol_basis: 'time_of_day_20' }));
    expect(chipPasses('relvol', tod)).toBe(true);
    expect(chipPasses('relvol', scannerRowFromLeaderboard(row({ rvol: 1.2, rvol_basis: 'daily_avg' })))).toBe(false);
  });
});
