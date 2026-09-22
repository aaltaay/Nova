import { describe, expect, it } from 'vitest';
import type { SimClockState } from './simClockTypes';
import { firstReplayMinute, formatMinuteClock, playheadTag, stripBandSegments } from './simStripFormat';

const session = {
  session_open_et: '2026-09-21T04:00:00-04:00',
  session_close_et: '2026-09-21T20:00:00-04:00',
  session_date: '2026-09-21',
};

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
