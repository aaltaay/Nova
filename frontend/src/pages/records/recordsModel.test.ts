import { describe, expect, it } from 'vitest';
import type { CaptureSessionRow } from '../../sim/useSimSessionController';
import { axisFor, daySummary, endedOf, gapKinds, hourTicks, unionSpans, type DayRecord } from './recordsModel';

/** Epoch seconds of an ET clock time on a summer day (EDT). */
const t = (hm: string) => Date.parse(`2026-07-15T${hm}:00-04:00`) / 1000;
const row = (over: Partial<CaptureSessionRow>): CaptureSessionRow => ({ symbol: 'ABC', prints: 1, l2: 1, usable: true, ...over });

describe('Records model (operator ask 2026-10-14)', () => {
  it('keeps one clock, 07:00-16:00 at least, widened to whole hours inside 04:00-20:00', () => {
    expect(axisFor([])).toEqual({ t0: 420, t1: 960 });
    expect(axisFor([[[t('04:30'), t('05:00')]], [[t('17:00'), t('18:10')]]])).toEqual({ t0: 240, t1: 1140 });
    expect(hourTicks({ t0: 420, t1: 960 })).toHaveLength(10);
    expect(hourTicks({ t0: 240, t1: 1200 })).toEqual([240, 360, 480, 600, 720, 840, 960, 1080, 1200]);
  });

  it('says who ended a recording, never a raw code', () => {
    expect(endedOf(row({ status: 'stopped_partial_ok', last_reason: 'operator' }), false)).toEqual({ words: 'Stopped by you', tone: 'muted' });
    expect(endedOf(row({ status: 'stopped_partial_ok', last_reason: 'auto' }), false).words).toBe('Stopped by auto-record');
    expect(endedOf(row({ status: 'stopped_partial_ok', last_reason: 'failure' }), false)).toEqual({ words: 'Stopped on its own', tone: 'bad' });
    expect(endedOf(row({ status: 'interrupted', last_reason: 'restart' }), false)).toEqual({ words: 'Cut by a Nova restart', tone: 'warn' });
    expect(endedOf(row({ status: 'stopped_partial_ok', last_reason: null }), false).words).toBe('Stopped');
    expect(endedOf(row({ status: 'recording', last_reason: 'restart' }), true)).toEqual({ words: 'Recording · resumed after a restart', tone: 'live' });
    expect(endedOf(row({ usable: false, empty: true, unavailable_reason: 'No recorded prints or quotes' }), false).words)
      .toBe('No recorded prints or quotes');
  });

  it('splits only the gaps the listing names: stopped on purpose apart from missing', () => {
    const r = row({ gaps: [[t('09:30'), t('09:40'), 'auto'], [t('10:00'), t('10:02'), 'restart'], [t('11:00'), t('11:01'), null]] });
    expect(gapKinds(r)).toEqual({
      planned: [[t('09:30'), t('09:40')]],
      missing: [[t('10:00'), t('10:02')], [t('11:00'), t('11:01')]],
    });
    expect(gapKinds(row({}))).toEqual({ planned: [], missing: [] });
  });

  it('totals a day: union of spans, uncounted prints left out, cut and stopped-by-you counted', () => {
    const recs: DayRecord[] = [
      row({ symbol: 'A', prints: 10, l2: 2, missing_sec: 30, status: 'interrupted', spans: [[t('09:00'), t('09:30')]],
        bytes: { prints: 10, l2: 20, quotes: 0 } }),
      row({ symbol: 'B', prints: null, l2: null, status: 'stopped_partial_ok', last_reason: 'operator',
        spans: [[t('09:20'), t('10:00')]] }),
    ].map(r => ({ date: '2026-07-15', row: r, live: false, ended: endedOf(r, false) }));
    const s = daySummary(recs);
    expect(s).toMatchObject({ count: 2, prints: 10, l2: 2, withGaps: 1, cut: 1, byYou: 1, recording: 0, bytes: 30 });
    expect(s.union).toEqual([[t('09:00'), t('10:00')]]);
    expect(s.recordedSec).toBe(3600);
    expect(unionSpans([[0, 10], [45, 50], [100, 110]])).toEqual([[0, 10], [45, 50], [100, 110]]);
    expect(unionSpans([[0, 10], [30, 50]])).toEqual([[0, 50]]);
  });
});
