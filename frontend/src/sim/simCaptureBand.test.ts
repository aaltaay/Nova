import { describe, expect, it, vi } from 'vitest';
import { captureBandSegments, captureCoverageLabel, captureMissingSeconds, missingLabel } from './simCoverage';
import type { SimClockState } from './simClockTypes';

// A 16-hour session: 04:00 to 20:00 ET.
const clock = (segments: SimClockState['replay_load'] extends infer T ? (T extends { segments?: infer S } ? S : never) : never): SimClockState => ({
  sim: true,
  session_open_et: '2026-09-21T04:00:00-04:00',
  session_close_et: '2026-09-21T20:00:00-04:00',
  replay_source: 'capture',
  replay_load: {
    l2_total: 0, l2_loaded: 0, l2_decimated: false, malformed_rows: 0, invalid_timestamp_rows: 0, invalid_rows: 0,
    legacy_schema: false, segments,
  },
});

const HOUR = 1 / 16;

describe('captureBandSegments', () => {
  it('draws each recording where it sat in the session, and the gaps between as gaps', () => {
    const band = captureBandSegments(clock([
      { started_et: '2026-09-21T09:00:00-04:00', stopped_et: '2026-09-21T10:00:00-04:00', reason: 'failure' },
      { started_et: '2026-09-21T11:00:00-04:00', stopped_et: '2026-09-21T12:00:00-04:00', reason: 'operator' },
    ]));
    expect(band).toHaveLength(3);
    expect(band[0]).toMatchObject({ kind: 'recorded', reason: null });
    expect(band[0].left).toBeCloseTo(5 * HOUR);
    expect(band[0].width).toBeCloseTo(HOUR);
    expect(band[1]).toMatchObject({ kind: 'gap', reason: 'failure' });
    expect(band[1].left).toBeCloseTo(6 * HOUR);
    expect(band[1].width).toBeCloseTo(HOUR);
    expect(band[2]).toMatchObject({ kind: 'recorded' });
  });

  it('an open segment runs to now and never past the close (C41); overlaps merge; nothing means nothing', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    try {
      // Recording since 19:00, read at 19:30: recorded to 19:30, not to 20:00.
      vi.setSystemTime(new Date('2026-09-21T19:30:00-04:00'));
      const live = captureBandSegments(clock([{ started_et: '2026-09-21T19:00:00-04:00', stopped_et: null }]));
      expect(live).toHaveLength(1);
      expect(live[0].left + live[0].width).toBeCloseTo(15.5 * HOUR);
      // A later day: the session is over, so it runs to the close.
      vi.setSystemTime(new Date('2026-09-22T09:00:00-04:00'));
      const open = captureBandSegments(clock([
        { started_et: '2026-09-21T19:00:00-04:00', stopped_et: null },
      ]));
      expect(open).toHaveLength(1);
      expect(open[0].left + open[0].width).toBeCloseTo(1);
    } finally {
      vi.useRealTimers();
    }
    const overlapping = captureBandSegments(clock([
      { started_et: '2026-09-21T09:00:00-04:00', stopped_et: '2026-09-21T10:00:00-04:00' },
      { started_et: '2026-09-21T09:30:00-04:00', stopped_et: '2026-09-21T10:30:00-04:00' },
    ]));
    expect(overlapping).toHaveLength(1);
    expect(captureBandSegments(clock([]))).toEqual([]);
    expect(captureBandSegments({ sim: true, replay_load: undefined })).toEqual([]);
  });
});

describe('captureMissingSeconds / captureCoverageLabel', () => {
  const two = clock([
    { started_et: '2026-09-21T11:46:35-04:00', stopped_et: '2026-09-21T11:47:27-04:00', reason: 'failure' },
    { started_et: '2026-09-21T12:03:39-04:00', stopped_et: '2026-09-21T12:40:00-04:00', reason: 'operator' },
  ]);
  const hhmm = (ts: number) => new Date(ts * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit',
  });

  it('counts only the time between recordings', () => {
    expect(captureMissingSeconds(two)).toBe(16 * 60 + 12);
    expect(captureMissingSeconds(clock([two.replay_load!.segments![0]]))).toBe(0);
  });

  it('labels the recording and its gap with why', () => {
    expect(captureCoverageLabel(two, hhmm)).toBe('Recorded 11:46–11:47, 12:03–12:40 · 16m 12s missing (failure)');
    expect(captureCoverageLabel(clock([]), hhmm)).toBe('');
  });

  it('a gap the operator made by stopping is not "missing" (C64)', () => {
    const stopped = clock([
      { started_et: '2026-09-21T09:00:00-04:00', stopped_et: '2026-09-21T09:30:00-04:00', reason: 'operator' },
      { started_et: '2026-09-21T14:42:00-04:00', stopped_et: '2026-09-21T15:00:00-04:00', reason: 'failure' },
      { started_et: '2026-09-21T15:05:00-04:00', stopped_et: '2026-09-21T15:10:00-04:00', reason: 'operator' },
    ]);
    expect(captureMissingSeconds(stopped)).toBe(5 * 60);
    expect(captureCoverageLabel(stopped, hhmm)).toMatch(/· 5m 00s missing \(failure\)$/);
  });

  it('segments that are not a list, or junk rows, read as no recording -- never a crash (C6)', () => {
    const junk = { ...clock([]), replay_load: { segments: {} as never } } as SimClockState;
    expect(captureBandSegments(junk)).toEqual([]);
    expect(captureMissingSeconds(junk)).toBe(0);
    expect(captureBandSegments(clock([null as never, 'x' as never, { started_et: 'bad', stopped_et: null }]))).toEqual([]);
  });

  it('missingLabel reads like a stopwatch', () => {
    expect(missingLabel(35)).toBe('35s');
    expect(missingLabel(252)).toBe('4m 12s');
    expect(missingLabel(3720)).toBe('1h 02m');
  });
});
