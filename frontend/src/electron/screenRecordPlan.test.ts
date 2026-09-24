/**
 * The trading screen recording's plan (ADR 035): what each monitor records at,
 * where the files go and what they are called.
 */
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  SCREEN_RECORD_DATA_DIR,
  SCREEN_RECORD_FREE_FAIL_BYTES,
  SCREEN_RECORD_FREE_WARN_BYTES,
  SCREEN_RECORD_MAX_BPS,
  SCREEN_RECORD_MIN_BPS,
  SCREEN_RECORD_RETRY_MS,
  bitrateFor,
  captureSize,
  diskState,
  etParts,
  extensionFor,
  nextBoundaryMs,
  planDisplays,
  resolveRecordDir,
  retryDelayMs,
  samePlan,
  segmentRelPath,
} from '../../electron/screenRecordPlan.mjs';

// The desk on 2026-09-24: a 4K monitor at 150% on the left, the 1440p primary, a 1200p above.
const LEFT_4K = { id: 3582477279, label: 'LG 4K', bounds: { x: -2560, y: -509, width: 2560, height: 1441 }, size: { width: 2560, height: 1441 }, scaleFactor: 1.5 };
const PRIMARY = { id: 3443810833, label: '', bounds: { x: 0, y: 0, width: 2560, height: 1440 }, size: { width: 2560, height: 1440 }, scaleFactor: 1 };
const ABOVE = { id: 4023004662, label: 'Dell', bounds: { x: 0, y: -1200, width: 1920, height: 1200 }, size: { width: 1920, height: 1200 }, scaleFactor: 1 };
const SOURCES = [
  { id: 'screen:1:0', display_id: '3443810833' },
  { id: 'screen:0:0', display_id: '4023004662' },
  { id: 'screen:2:0', display_id: '3582477279' },
];

describe('captureSize', () => {
  it('records a scaled monitor at its Windows layout size, even on both sides', () => {
    expect(captureSize(LEFT_4K)).toEqual({ width: 2560, height: 1440 });
    expect(captureSize(ABOVE)).toEqual({ width: 1920, height: 1200 });
  });

  it('caps a larger screen at 3840x2160, keeping its shape', () => {
    expect(captureSize({ size: { width: 5120, height: 2880 } })).toEqual({ width: 3840, height: 2160 });
    expect(captureSize({ size: { width: 7680, height: 2160 } })).toEqual({ width: 3840, height: 1080 });
  });
});

describe('bitrateFor', () => {
  it('scales with pixels and frame rate, inside the bounds', () => {
    expect(bitrateFor(2560, 1440, 15)).toBe(2_488_320);
    expect(bitrateFor(640, 480, 15)).toBe(SCREEN_RECORD_MIN_BPS);
    expect(bitrateFor(7680, 4320, 30)).toBe(SCREEN_RECORD_MAX_BPS);
  });
});

describe('planDisplays', () => {
  it('numbers monitors left to right and ties each to its screen source', () => {
    const { plans, unmatched } = planDisplays({ displays: [PRIMARY, ABOVE, LEFT_4K], sources: SOURCES, primaryId: PRIMARY.id });
    expect(unmatched).toEqual([]);
    expect(plans.map((p) => [p.display.index, p.sourceId, p.width, p.height, p.display.primary])).toEqual([
      [1, 'screen:2:0', 2560, 1440, false],
      [2, 'screen:0:0', 1920, 1200, false],
      [3, 'screen:1:0', 2560, 1440, true],
    ]);
    expect(plans[0].display).toMatchObject({ id: '3582477279', count: 3, label: 'LG 4K', scale_factor: 1.5 });
  });

  it('names a monitor with no screen source instead of guessing one', () => {
    const { plans, unmatched } = planDisplays({ displays: [PRIMARY, ABOVE], sources: SOURCES.slice(0, 1), primaryId: PRIMARY.id });
    expect(plans.map((p) => p.display.index)).toEqual([2]);
    expect(unmatched.map((d) => d.index)).toEqual([1]);
  });

  it('records the only screen even when Windows gives it no display id', () => {
    const { plans, unmatched } = planDisplays({ displays: [PRIMARY], sources: [{ id: 'screen:0:0', display_id: '' }], primaryId: PRIMARY.id });
    expect(plans).toHaveLength(1);
    expect(plans[0].sourceId).toBe('screen:0:0');
    expect(unmatched).toEqual([]);
  });

  it('treats an unchanged or renumbered monitor as the same plan, a resized one as new', () => {
    const a = planDisplays({ displays: [PRIMARY], sources: SOURCES, primaryId: PRIMARY.id }).plans[0];
    const b = planDisplays({ displays: [{ ...PRIMARY, label: 'renamed' }], sources: SOURCES, primaryId: PRIMARY.id }).plans[0];
    const moved = planDisplays({ displays: [PRIMARY, LEFT_4K], sources: SOURCES, primaryId: PRIMARY.id }).plans[1];
    const c = planDisplays({ displays: [{ ...PRIMARY, size: { width: 1920, height: 1080 } }], sources: SOURCES, primaryId: PRIMARY.id }).plans[0];
    expect(moved.display.index).toBe(2);
    expect(samePlan(a, b)).toBe(true);
    expect(samePlan(a, moved)).toBe(true);
    expect(samePlan(a, c)).toBe(false);
  });
});

describe('resolveRecordDir', () => {
  const base = { userData: 'C:\\Users\\op\\AppData\\Roaming\\nova', join: path.win32.join };

  it('prefers NOVA_SCREEN_RECORD_DIR, then F:, then the app folder with a note', () => {
    expect(resolveRecordDir({ ...base, env: { NOVA_SCREEN_RECORD_DIR: 'G:\\rec' }, dataDriveMounted: true }))
      .toEqual({ dir: 'G:\\rec', source: 'env', note: null });
    expect(resolveRecordDir({ ...base, env: {}, dataDriveMounted: true }))
      .toEqual({ dir: SCREEN_RECORD_DATA_DIR, source: 'data_drive', note: null });
    const fallback = resolveRecordDir({ ...base, env: {}, dataDriveMounted: false });
    expect(fallback.dir).toBe('C:\\Users\\op\\AppData\\Roaming\\nova\\screen');
    expect(fallback.source).toBe('fallback');
    expect(fallback.note).toMatch(/F: is not mounted/);
  });
});

describe('file names and boundaries', () => {
  // 2026-09-24 09:45:00 ET (EDT, UTC-4)
  const t = Date.UTC(2026, 8, 24, 13, 45, 0);

  it('names a segment by its Eastern date and start time', () => {
    expect(etParts(t)).toEqual({ date: '2026-09-24', time: '094500' });
    expect(segmentRelPath(t, 2, 'video/x-matroska;codecs=avc1')).toEqual({ date: '2026-09-24', name: '094500-screen2.mkv' });
    expect(segmentRelPath(t, 1, 'video/webm;codecs=vp9', 2).name).toBe('094500-screen1-2.webm');
    // 23:59:59 ET on the 24th is still the 24th, though UTC is the 25th.
    expect(etParts(Date.UTC(2026, 8, 25, 3, 59, 59)).date).toBe('2026-09-24');
  });

  it('rotates on the next quarter hour', () => {
    expect(nextBoundaryMs(t)).toBe(t + 15 * 60_000);
    expect(nextBoundaryMs(t + 1)).toBe(t + 15 * 60_000);
    expect(nextBoundaryMs(t - 1)).toBe(t);
  });

  it('writes H.264 as Matroska and VP8 / VP9 as WebM', () => {
    expect(extensionFor('video/x-matroska;codecs=avc1')).toBe('mkv');
    expect(extensionFor('video/webm;codecs=h264')).toBe('mkv');
    expect(extensionFor('video/webm;codecs=vp8')).toBe('webm');
  });
});

describe('guards', () => {
  it('judges the drive like the leaderboard does', () => {
    expect(diskState(null)).toBe('unknown');
    expect(diskState(SCREEN_RECORD_FREE_FAIL_BYTES - 1)).toBe('fail');
    expect(diskState(SCREEN_RECORD_FREE_WARN_BYTES - 1)).toBe('warn');
    expect(diskState(SCREEN_RECORD_FREE_WARN_BYTES)).toBe('ok');
  });

  it('backs off and then keeps retrying at the longest wait, never giving up', () => {
    expect(retryDelayMs(1)).toBe(SCREEN_RECORD_RETRY_MS[0]);
    expect(retryDelayMs(3)).toBe(SCREEN_RECORD_RETRY_MS[2]);
    expect(retryDelayMs(500)).toBe(SCREEN_RECORD_RETRY_MS[SCREEN_RECORD_RETRY_MS.length - 1]);
  });
});
