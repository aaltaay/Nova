import { describe, expect, it } from 'vitest';
import type { SimClockState } from './simClockTypes';
import {
  firstReplayMinute, formatMinuteClock, playheadTag, recordedLane, stripBandSegments, stripScale,
} from './simStripFormat';

const session = {
  session_open_et: '2026-09-21T04:00:00-04:00',
  session_close_et: '2026-09-21T20:00:00-04:00',
  session_date: '2026-09-21',
};
const CLOSE_FOR_GARBAGE = '2026-09-21T11:30:00-04:00';

const capture: SimClockState = {
  sim: true, replay_source: 'capture', minute_max: 960, ...session,
  replay_load: {
    l2_total: 0, l2_loaded: 0, l2_decimated: false, malformed_rows: 0, invalid_timestamp_rows: 0, invalid_rows: 0,
    legacy_schema: false,
    segments: [
      { started_et: '2026-09-21T07:30:00-04:00', stopped_et: '2026-09-21T09:48:00-04:00', reason: 'failure' },
      { started_et: '2026-09-21T10:05:00-04:00', stopped_et: null },
    ],
  },
};

describe('playheadTag', () => {
  it('is empty at the live edge -- the global bar clock is the truth there', () => {
    expect(playheadTag({ sim: true, live_edge: true, sim_time_et: '2026-09-21T18:14:07-04:00', ...session }, null, '2026-09-21')).toBe('');
  });

  it('shows the playhead time off the edge, and the date only when the session is not today', () => {
    const clock: SimClockState = { sim: true, live_edge: false, sim_time_et: '2026-09-21T11:42:10-04:00', ...session };
    expect(playheadTag(clock, null, '2026-09-21')).toBe('11:42:10');
    expect(playheadTag(clock, null, '2026-09-22')).toBe('11:42:10 · Sep 21');
    expect(playheadTag(clock, 462, '2026-09-21')).toBe('11:42:00');
  });
});

describe('stripBandSegments', () => {
  it('draws a capture as recorded stretches and striped gaps', () => {
    const segments = stripBandSegments(capture, null, () => '');
    expect(segments.map(s => s.kind)).toEqual(['recorded', 'gap', 'recorded']);
    expect(segments[0].left).toBeCloseTo(3.5 / 16);
    expect(segments[1].title).toMatch(/stopped on its own/);
  });

  it('draws a failed replay as one red stretch that names the error', () => {
    const segments = stripBandSegments({ ...capture, replay_ok: false, replay_error: 'no usable prints' }, null, () => '');
    expect(segments).toEqual([{ left: 0, width: 1, kind: 'failed', title: 'Replay failed: no usable prints' }]);
  });

  it('draws a historical window from its downloaded ranges against the session', () => {
    const open = Date.parse(session.session_open_et) / 1000;
    const selection = { symbol: 'IMCC', date: '2026-09-21', start: '09:15', end: '11:30', coverage_through: 0,
      start_ts: open + 5.25 * 3600, end_ts: open + 7.5 * 3600, coverage: [[open + 5.25 * 3600, open + 6 * 3600]] };
    const segments = stripBandSegments({ sim: true, replay_source: 'historical', ...session }, selection, ts => String(ts));
    expect(segments).toHaveLength(1);
    expect(segments[0].kind).toBe('downloaded');
    expect(segments[0].left).toBeCloseTo(5.25 / 16);
    expect(segments[0].width).toBeCloseTo(0.75 / 16);
  });

  it('draws nothing with nothing loaded', () => {
    expect(stripBandSegments({ sim: true, replay_source: 'none', ...session }, null, () => '')).toEqual([]);
  });
});

describe('stripScale (V10 / C27: the band is labelled on the scale it is drawn on)', () => {
  it('the default 04:00-20:00 session: its bounds, regular hours and both ticks', () => {
    const scale = stripScale({ sim: true, ...session });
    expect(scale.openLabel).toBe('04:00');
    expect(scale.closeLabel).toBe('20:00');
    expect(scale.rth?.left).toBeCloseTo(5.5 / 16);
    expect(scale.rth?.width).toBeCloseTo(6.5 / 16);
    expect(scale.ticks.map(tick => tick.label)).toEqual(['09:30', '16:00']);
    expect(scale.ticks[1].left).toBeCloseTo(12 / 16);
  });

  it('a loaded 09:15-11:30 window: its own bounds, the 09:30 tick where it falls, no 16:00 tick', () => {
    const scale = stripScale({
      sim: true, session_open_et: '2026-09-21T09:15:00-04:00', session_close_et: '2026-09-21T11:30:00-04:00',
    });
    expect(scale.openLabel).toBe('09:15');
    expect(scale.closeLabel).toBe('11:30');
    expect(scale.ticks).toHaveLength(1);
    expect(scale.ticks[0].label).toBe('09:30');
    expect(scale.ticks[0].left).toBeCloseTo(15 / 135);
    expect(scale.rth?.left).toBeCloseTo(15 / 135);
    expect((scale.rth?.left ?? 0) + (scale.rth?.width ?? 0)).toBeCloseTo(1);
  });

  it('a window wholly outside regular hours has no underlay and no ticks; no window reads as the default', () => {
    const post = stripScale({
      sim: true, session_open_et: '2026-09-21T16:30:00-04:00', session_close_et: '2026-09-21T19:00:00-04:00',
    });
    expect(post.rth).toBeNull();
    expect(post.ticks).toEqual([]);
    expect(stripScale(null).openLabel).toBe('04:00');
    expect(stripScale({ sim: true, session_open_et: 'garbage', session_close_et: CLOSE_FOR_GARBAGE }).closeLabel).toBe('20:00');
  });

  it('places the playhead, the downloaded ranges and the scale on one domain', () => {
    const openTs = Date.parse('2026-09-21T09:15:00-04:00') / 1000;
    const clock: SimClockState = {
      sim: true, replay_source: 'historical', minute_max: 135, minute_from_open: 58,
      session_open_et: '2026-09-21T09:15:00-04:00', session_close_et: '2026-09-21T11:30:00-04:00',
    };
    const selection = { symbol: 'GRML', date: '2026-09-21', start: '09:15', end: '11:30', coverage_through: 0,
      start_ts: openTs, end_ts: openTs + 135 * 60, coverage: [[openTs, openTs + 58 * 60]] };
    const [downloaded] = stripBandSegments(clock, selection, () => '');
    // The downloaded edge (10:13) and the playhead (minute 58 of 135) sit at the same fraction.
    expect(downloaded.left + downloaded.width).toBeCloseTo(58 / 135);
  });
});

describe('firstReplayMinute', () => {
  it('is the first recorded minute of a capture, the window start of a historical replay, else 0', () => {
    expect(firstReplayMinute(capture, null)).toBe(210);
    const open = Date.parse(session.session_open_et) / 1000;
    expect(firstReplayMinute({ sim: true, replay_source: 'historical', ...session },
      { symbol: 'X', date: '', start: '', end: '', coverage_through: 0, start_ts: open + 315 * 60 })).toBe(315);
    expect(firstReplayMinute({ sim: true, replay_source: 'none' }, null)).toBe(0);
  });
});

describe('formatMinuteClock', () => {
  it('offsets from the session open', () => {
    expect(formatMinuteClock(462)).toBe('11:42:00');
    expect(formatMinuteClock(0, '09:30')).toBe('09:30:00');
  });
});

describe('recordedLane (operator ask, 2026-09-22: show where Nova recorded)', () => {
  const open = Date.parse(session.session_open_et) / 1000;
  const hhmm = (ts: number) => new Date(ts * 1000).toISOString().slice(11, 16);
  const sessions = {
    days: [{ date: '2026-09-21', ticker_count: 1 }],
    tickers_by_day: {
      '2026-09-21': [
        { symbol: 'GRML', prints: 10, l2: 0, spans: [[open + 5 * 3600, open + 6 * 3600], [open + 5.5 * 3600, open + 7 * 3600]] },
      ],
    },
  };

  it('draws the recorded spans of the loaded replay symbol, merged, as fractions of the session', () => {
    const clock: SimClockState = { sim: true, replay_source: 'historical', replay_symbol: 'GRML', replay_date: '2026-09-21', ...session };
    const lane = recordedLane(clock, sessions, 'TOPS', hhmm)!;
    expect(lane.symbol).toBe('GRML');
    expect(lane.segments).toHaveLength(1);
    expect(lane.segments[0].left).toBeCloseTo(5 / 16);
    expect(lane.segments[0].width).toBeCloseTo(2 / 16);
    expect(lane.title).toMatch(/^Recorded by Nova: GRML /);
  });

  it('falls back to the active tab and says plainly when nothing was recorded', () => {
    const clock: SimClockState = { sim: true, live_edge: true, ...session };
    const lane = recordedLane(clock, sessions, 'tops', hhmm)!;
    expect(lane.symbol).toBe('TOPS');
    expect(lane.segments).toEqual([]);
    expect(lane.title).toMatch(/Not recorded by Nova: no Session Record for TOPS on Sep 21/);
  });

  it('says nothing, rather than "not recorded", for a recording it cannot place in time', () => {
    const clock: SimClockState = { sim: true, replay_symbol: 'GRML', replay_date: '2026-09-21', ...session };
    const older = { days: [], tickers_by_day: { '2026-09-21': [{ symbol: 'GRML', prints: 3, l2: 0 }] } };
    expect(recordedLane(clock, older, null, hhmm)).toBeNull();
    const noSegments = { days: [], tickers_by_day: { '2026-09-21': [{ symbol: 'GRML', prints: 3, l2: 0, spans: [] }] } };
    expect(recordedLane(clock, noSegments, null, hhmm)).toBeNull();
  });

  it('is null without a symbol or session bounds', () => {
    expect(recordedLane(null, sessions, 'GRML', hhmm)).toBeNull();
    expect(recordedLane({ sim: true, ...session }, sessions, null, hhmm)).toBeNull();
    expect(recordedLane({ sim: true, session_date: '2026-09-21' }, sessions, 'GRML', hhmm)).toBeNull();
  });
});
