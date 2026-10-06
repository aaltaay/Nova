import { describe, expect, it } from 'vitest';
import { parseCaptureSessions } from './captureSessionsParse';
import { coverageFraction, coverageSegments, captureBandSegments } from './simCoverage';
import { parseHistoricalSnapshot, parseHistoricalStatus, parseMassiveDays, parseSimClock } from './simPayloadParse';

const OPEN = '2026-09-21T09:15:00-04:00';
const CLOSE = '2026-09-21T11:30:00-04:00';

describe('parseSimClock (C6)', () => {
  it('keeps a well-formed clock as it is', () => {
    const clock = parseSimClock({
      sim: true, sim_time_et: '2026-09-21T10:00:00-04:00', session_open_et: OPEN, session_close_et: CLOSE,
      minute_from_open: 45, minute_max: 135, live_edge: false, replay_source: 'capture', replay_symbol: 'GRML',
      replay_ok: true, replay_loading: false, second_max: 8100,
      replay_load: { l2_total: 3, l2_loaded: 3, segments: [{ started_et: OPEN, stopped_et: null, reason: null }] },
    });
    expect(clock).toMatchObject({ sim: true, minute_from_open: 45, replay_symbol: 'GRML', second_max: 8100 });
    expect(clock.replay_load?.segments).toEqual([{ started_et: OPEN, stopped_et: null, reason: null }]);
  });

  it('reads a segments object, junk segments and wrong-typed fields as absent -- never a crash', () => {
    const clock = parseSimClock({
      sim: true, session_open_et: OPEN, session_close_et: CLOSE, replay_source: 'capture',
      replay_symbol: 42, phase: 7, minute_from_open: 'ten', replay_ok: 'yes',
      replay_load: { segments: {} },
    });
    expect(clock.replay_symbol).toBeUndefined();
    expect(clock.phase).toBeUndefined();
    expect(clock.minute_from_open).toBeUndefined();
    expect(clock.replay_ok).toBeUndefined();
    expect(clock.replay_load?.segments).toEqual([]);
    expect(captureBandSegments(clock)).toEqual([]);
    const junk = parseSimClock({ sim: true, replay_load: { segments: [null, 'x', { started_et: 5 }, { started_et: OPEN, stopped_et: 9 }] } });
    expect(junk.replay_load?.segments).toEqual([]);
  });

  it('keeps an explicit null (a capture still loading reports replay_ok: null)', () => {
    const clock = parseSimClock({ sim: true, replay_ok: null, replay_loading: true, replay_symbol: null });
    expect(clock.replay_ok).toBeNull();
    expect(clock.replay_loading).toBe(true);
    expect(clock.replay_symbol).toBeNull();
  });

  it('refuses a body that is not an object at all', () => {
    expect(() => parseSimClock(null)).toThrow(/unreadable Sim clock/);
    expect(() => parseSimClock([])).toThrow(/unreadable/);
  });
});

describe('parseHistoricalStatus (C6 / C7)', () => {
  const start = Date.parse(OPEN) / 1000;
  const end = Date.parse(CLOSE) / 1000;

  it('keeps only well-formed coverage pairs, so the band and the fraction never crash', () => {
    const status = parseHistoricalStatus({
      jobs: [],
      selection: { symbol: 'GRML', date: '2026-09-21', start: '09:15', end: '11:30', start_ts: start, end_ts: end,
        coverage_through: start, coverage: [null, [start, start + 600], [5], 'x', [start + 900, start + 900]] },
    });
    expect(status.selection?.coverage).toEqual([[start, start + 600]]);
    expect(coverageFraction(status.selection)).toBeCloseTo(600 / (end - start));
    expect(coverageSegments(status.selection)).toHaveLength(1);
  });

  it('a job without a count reads as unknown, a job without an id is dropped', () => {
    const status = parseHistoricalStatus({
      jobs: [
        { id: 'a', kind: 'trades', status: 'running', count: null, pages: 'x', symbol: 'GRML', date: '2026-09-21', start: '09:15', end: '11:30' },
        { kind: 'trades', status: 'failed' },
        null,
      ],
    });
    expect(status.jobs).toHaveLength(1);
    expect(status.jobs[0].count).toBeNull();
    expect(status.jobs[0].pages).toBeNull();
    expect(status.selection).toBeUndefined();
  });

  it('a list or a missing jobs field reads as no jobs; a non-object body is refused', () => {
    expect(parseHistoricalStatus({ jobs: {}, selection: 'x' })).toMatchObject({ jobs: [], selection: null });
    expect(() => parseHistoricalStatus([])).toThrow(/unreadable/);
  });
});

describe('parseHistoricalSnapshot (C9)', () => {
  it('prints: null reads as no prints, and junk rows are skipped', () => {
    expect(parseHistoricalSnapshot({ active: true, symbol: 'GDC', prints: null }).prints).toEqual([]);
    const snap = parseHistoricalSnapshot({
      active: true, symbol: 'GDC', as_of: '2026-09-21T10:00:00-04:00',
      prints: [{ time: '2026-09-21T14:00:00Z', price: 2.1, size: 100, exchange: 'ISLAND', side: 'sideways' }, { price: 'x' }, 7],
      depth: { bids: 'no' },
    });
    expect(snap.prints).toHaveLength(1);
    expect(snap.prints[0].side).toBeNull();
    expect(snap.depth).toBeNull();
  });

  it('a recorded book keeps only real levels', () => {
    const snap = parseHistoricalSnapshot({
      active: true, symbol: 'GDC', prints: [],
      depth: { symbol: 'GDC', ts: 1_790_000_000, age_sec: 1, source: 'l2_recorder',
        bids: [{ price: 2, size: 100 }, { price: null, size: 5 }], asks: null },
    });
    expect(snap.depth?.bids).toEqual([{ price: 2, size: 100, side: 'bid' }]);
    expect(snap.depth?.asks).toEqual([]);
  });
});

describe('parseCaptureSessions (C13 / C21 / C22)', () => {
  it('a listing without tickers_by_day, or with a list there, reads as no Session Records', () => {
    expect(parseCaptureSessions({ days: [{ date: '2026-09-21', ticker_count: 1 }] })).toMatchObject({
      days: [{ date: '2026-09-21', ticker_count: 1 }], tickers_by_day: {},
    });
    expect(parseCaptureSessions({ tickers_by_day: [] }).tickers_by_day).toEqual({});
    expect(() => parseCaptureSessions([])).toThrow(/unreadable Session Record listing/);
  });

  it('an uncounted -1 is unknown, a row without a symbol is skipped, the source rides along', () => {
    const parsed = parseCaptureSessions({
      days: [],
      tickers_by_day: {
        '2026-09-19': [
          { symbol: 'sim1', prints: 172020, l2: -1, usable: true, source: 'sim', spans: [[1, 2], null] },
          { symbol: 'GDC', prints: -1, l2: 3, usable: true, status: 'recording', segments: 1 },
          { prints: 5 },
          'junk',
        ],
        '2026-09-18': 'not a list',
      },
    });
    const rows = parsed.tickers_by_day['2026-09-19'];
    expect(rows.map(row => row.symbol)).toEqual(['SIM1', 'GDC']);
    expect(rows[0]).toMatchObject({ prints: 172020, l2: null, source: 'sim', spans: [[1, 2]] });
    expect(rows[1]).toMatchObject({ prints: null, status: 'recording', segments: 1 });
    expect(parsed.tickers_by_day['2026-09-18']).toEqual([]);
  });
});

describe('the Massive fields (ADR 046)', () => {
  it("a snapshot keeps the NBBO and each print's price verdict; junk reads as absent", () => {
    const snap = parseHistoricalSnapshot({
      active: true, symbol: 'IMCC', prints: [
        { time: '2026-09-18T13:30:00.25Z', price: 9.5, size: 10, exchange: 'NASDAQ', sets_price: false },
        { time: '2026-09-18T13:30:00.1Z', price: 10, size: 100, exchange: 'NASDAQ', sets_price: true },
      ],
      bid: 10, ask: 10.02, bid_size: 100, ask_size: 'x', quote_ts: 1_790_000_000, quote_source: 'massive_nbbo',
      quote_status: 'complete', sides_nbbo: 2,
    });
    expect([snap.bid, snap.ask, snap.bid_size, snap.ask_size]).toEqual([10, 10.02, 100, null]);
    expect([snap.quote_source, snap.quote_status, snap.sides_nbbo]).toEqual(['massive_nbbo', 'complete', 2]);
    expect(snap.prints.map(p => p.sets_price)).toEqual([false, undefined]);
    expect(parseHistoricalSnapshot({ active: true, symbol: 'X', prints: [], quote_status: 'weird' }).quote_status).toBeNull();
  });

  it('a listing keeps the import fields and the Massive summary; an older API has none', () => {
    const status = parseHistoricalStatus({
      jobs: [{ id: 'm', kind: 'trades', status: 'running', symbol: 'IMCC', date: '2026-09-18', start: '09:30', end: '10:00',
        source: 'massive', stage: 'reading', stages: { trades_v1: 50, quotes_v1: 'x' }, quote_status: null }],
      massive: { available: true, reason: null, trade_days: 2600, quote_days: 300, first: '2016-01-04', last: '2026-10-02' },
    });
    expect(status.jobs[0]).toMatchObject({ source: 'massive', stage: 'reading', stages: { trades_v1: 50 }, quote_status: null });
    expect(status.massive).toEqual({ available: true, reason: null, trade_days: 2600, quote_days: 300,
      first: '2016-01-04', last: '2026-10-02', store_error: null });
    expect(parseHistoricalStatus({ jobs: [] }).massive).toBeUndefined();
  });

  it('the day list keeps real dates only', () => {
    expect(parseMassiveDays({ available: true, days: [
      { date: '2016-01-05', trades: true, quotes: 'yes', minute_aggs: true }, { date: 'tomorrow' }, 3,
    ] })).toEqual({ available: true, reason: null,
      days: [{ date: '2016-01-05', trades: true, quotes: false, minute_aggs: true }] });
    expect(() => parseMassiveDays(null)).toThrow();
  });
});
