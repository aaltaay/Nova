import { describe, expect, it } from 'vitest';
import { bySecondNotice, bySecondStands, gappersBySecondDay, withGappersBySecond } from './gappersBySecond';
import { parseLeaderboardSecondsAt } from './leaderboardParse';
import { replayFromAnswer } from './leaderboardRows';
import type { LeaderboardSecondsAt, ScannerReplay } from './leaderboardTypes';

const epoch = (time: string) => Date.parse(`2026-09-01T${time}-04:00`) / 1000;
const DAY = '2026-09-01';

const minuteBoard = (source: 'reconstructed' | 'recorded', boards: string[] = ['market', 'gappers']): ScannerReplay =>
  replayFromAnswer(DAY, epoch('07:45:00'), {
    date: DAY, at: epoch('07:45:00'), source, minute_ts: epoch('07:45:00'), covered: true, gap: null,
    boards: Object.fromEntries(boards.map(name => [name, {
      state: 'rebuilt',
      rows: [{ symbol: name === 'gappers' ? 'HKPD' : 'GPRO', minute_ts: null, board: name, source, rank: 1,
        price: 0.5009, prev_close: 0.3333, change_pct: 0.5029, volume: 1, rvol: null, rvol_basis: null,
        float_shares: null, has_news: null, news_first_seen_ts: null, halted: null, gap_pct: 0.5029,
        exchange: null, market_cap: null, catalyst: null }],
    }])),
    leaders: [], catalyst_symbols: 0,
  });

const atSecond = (time: string, symbols: string[], over: Partial<LeaderboardSecondsAt> = {}): LeaderboardSecondsAt =>
  parseLeaderboardSecondsAt({
    date: DAY, status: 'ready', second_ts: epoch(time), minute_ts: epoch('07:45:00'), state: 'rebuilt',
    rows: symbols.map((symbol, i) => ({ symbol, rank: i + 1, price: 0.82, prev_close: 0.6727, change_pct: 0.219 })),
    ...over,
  });

describe('Gappers by the second over the minute board', () => {
  it('only a rebuilt day with a Gappers list can have it', () => {
    expect(gappersBySecondDay(minuteBoard('reconstructed'))).toBe(DAY);
    expect(gappersBySecondDay(minuteBoard('reconstructed', ['market']))).toBeNull();
    expect(gappersBySecondDay(minuteBoard('recorded'))).toBeNull();
    expect(gappersBySecondDay(null)).toBeNull();
  });

  it('a second stands only at or just behind the playhead, never ahead of it', () => {
    const answer = atSecond('07:45:58', ['KALA']);
    expect(bySecondStands(answer, epoch('07:45:58'))).toBe(true);
    expect(bySecondStands(answer, epoch('07:46:00'))).toBe(true);
    expect(bySecondStands(answer, epoch('07:46:01'))).toBe(false);      // the playhead jumped on
    expect(bySecondStands(answer, epoch('07:45:57'))).toBe(false);      // scrubbed back past it
    expect(bySecondStands({ ...answer, status: 'building' }, epoch('07:45:58'))).toBe(false);
  });

  it('replaces only the Gappers list, and says which second it is at', () => {
    const board = minuteBoard('reconstructed');
    const shown = withGappersBySecond(board, { date: DAY, asked: epoch('07:45:58'), answer: atSecond('07:45:58', ['KALA']), error: null },
      epoch('07:45:58'));
    expect(shown?.tables.gappers.map(r => r.symbol)).toEqual(['KALA']);
    expect(shown?.tables.gainers).toBe(board.tables.gainers);
    expect(shown?.bySecond).toMatchObject({ shown: true, status: 'ready', secondTs: epoch('07:45:58') });
    expect(bySecondNotice(shown?.bySecond)).toBe('Gappers by the second · 07:45:58 ET');
  });

  it('keeps the minute board while the second is not there yet, and says why', () => {
    const board = minuteBoard('reconstructed');
    const building = parseLeaderboardSecondsAt({ date: DAY, status: 'building', stage: 'trades', done: 12, total: 61 });
    const shown = withGappersBySecond(board, { date: DAY, asked: null, answer: building, error: null }, epoch('07:45:58'));
    expect(shown?.tables.gappers.map(r => r.symbol)).toEqual(['HKPD']);
    expect(bySecondNotice(shown?.bySecond)).toBe('Gappers by the second: reading trades 12 of 61 stocks… (per minute until then)');
    const other = withGappersBySecond(board, { date: '2026-09-02', asked: null, answer: atSecond('07:45:58', ['KALA']), error: null },
      epoch('07:45:58'));
    expect(other).toBe(board);
  });

  it('every state reads in words; nothing asked yet says nothing', () => {
    const notice = (over: Record<string, unknown>) =>
      bySecondNotice({ status: 'none', reason: null, stage: null, done: null, total: null, error: null, secondTs: null,
        shown: false, ...over } as never);
    expect(notice({})).toBeNull();
    expect(notice({ status: 'queued' })).toBe('Gappers by the second: starting… (per minute until then)');
    expect(notice({ status: 'building', stage: 'index' }))
      .toBe('Gappers by the second: indexing the day\'s trades file… (per minute until then)');
    expect(notice({ status: 'failed', error: 'disk gone' })).toBe('Gappers by the second failed: disk gone -- per minute');
    expect(notice({ status: 'unavailable', reason: 'The day\'s Massive trades file is not on disk' }))
      .toBe('Gappers per minute: The day\'s Massive trades file is not on disk');
    expect(notice({ status: 'error', error: 'Could not reach Nova.' }))
      .toBe('Gappers by the second did not load: Could not reach Nova. -- per minute');
    expect(notice({ status: 'stopped' })).toContain('reopen this day');
  });

  it('parses rows only from a ready answer that names its second', () => {
    expect(atSecond('07:45:58', ['KALA']).rows.map(r => r.symbol)).toEqual(['KALA']);
    expect(parseLeaderboardSecondsAt({ status: 'ready', second_ts: null, rows: [{ symbol: 'KALA' }] }).rows).toEqual([]);
    expect(parseLeaderboardSecondsAt({ status: 'building', second_ts: 5, rows: [{ symbol: 'KALA' }] }).rows).toEqual([]);
    expect(parseLeaderboardSecondsAt({ status: 'what' }).status).toBe('none');
    expect(() => parseLeaderboardSecondsAt('nope')).toThrow();
  });
});
