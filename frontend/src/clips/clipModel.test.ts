/**
 * Share clips on the desk (ADR 039), the pure half: the wire view is read
 * once, a chip says what its clip is doing, the Record menu locks what it
 * cannot do and says why, and a Records row reads in words.
 */
import { describe, expect, it } from 'vitest';
import { chipModel, clockLabel, hiddenWords, pictureWords, sourcesWords, statusWords, videoMenuState } from './clipModel';
import { readClipsView, type ClipRowView, type OpenClip } from './clipsView';
import { clampSelection, coverLine, defaultSettings, outputParts, sourceLine, timelineScale, timelineTicks, xWarning } from './clipExportModel';

const T0 = 1_790_000_000;
const wire = (over: Record<string, unknown> = {}) => ({
  schema_version: 1,
  generated_at: T0 + 72,
  dir: 'F:\\Nova\\clips',
  dir_source: 'data_drive',
  hq_max: 2,
  hq_in_use: 1,
  hq_max_sec: 1800,
  hq_warn_sec: 60,
  last_n_sec: 300,
  open: [{ clip_id: 'c1', symbol: 'PFSA', started_ts: T0, state: 'ok', screen_recording: true, hq: { since: T0, ends_at: T0 + 1800, recording: true, lost: false } }],
  clips: [{ clip_id: 'c1', symbol: 'PFSA', started_ts: T0, status: 'recording', length_sec: 72 }, { clip_id: 'bad' }],
  tabs: [{ window_id: 'main', symbol: 'PFSA', visible: true, display_id: 'd3', screen_recording: true }],
  disk: { free_bytes: 790 * 1024 ** 3, state: 'ok' },
  ...over,
});
const openOf = (over: Partial<OpenClip> = {}): OpenClip => ({
  clipId: 'c1', symbol: 'PFSA', startedTs: T0, state: 'ok', reason: null, showing: null, windowId: 'main', screenRecording: true, hq: null, ...over,
});
const rowOf = (over: Partial<ClipRowView> = {}): ClipRowView => ({
  clipId: 'c1', symbol: 'PFSA', origin: 'button', picture: 'trader_tab', startedTs: T0, endedTs: T0 + 198, lengthSec: 198,
  status: 'not_exported', hqSec: 0, hiddenSec: 0, gapSec: 0, export: null, ...over,
});

describe('readClipsView', () => {
  it('reads the view and drops what it cannot read', () => {
    const v = readClipsView(wire())!;
    expect(v.open[0]).toMatchObject({ clipId: 'c1', symbol: 'PFSA', hq: { endsAt: T0 + 1800, recording: true } });
    expect(v.clips).toHaveLength(1);
    expect(v.tabs[0]).toMatchObject({ symbol: 'PFSA', screenRecording: true });
    expect(readClipsView({ ...wire(), schema_version: 2 })).toBeNull();
  });
});

describe('clockLabel', () => {
  it('counts minutes, then hours', () => {
    expect(clockLabel(40)).toBe('0:40');
    expect(clockLabel(760)).toBe('12:40');
    expect(clockLabel(3723)).toBe('1:02:03');
  });
});

describe('chipModel', () => {
  it('counts up a cut clip, quietly', () => {
    const m = chipModel(openOf(), T0 + 192, 60);
    expect(m).toMatchObject({ tone: 'rec', time: '3:12', hq: false, extra: null });
    expect(m.lines).toContain('Frames: cut from the screen recording');
  });

  it("counts down High quality's last minute, and says the clip goes on", () => {
    const m = chipModel(openOf({ hq: { since: T0, endsAt: T0 + 1800, recording: true, lost: false, error: null, retryAt: null } }), T0 + 1742, 60);
    expect(m).toMatchObject({ tone: 'warn', extra: 'HQ 0:58', hq: true });
    expect(m.lines.join(' ')).toMatch(/goes on as a cut/);
  });

  it('dims a hidden tab and says why, and is loud only with no picture', () => {
    expect(chipModel(openOf({ state: 'hidden', reason: 'symbol', showing: 'APUS' }), T0 + 5, 60)).toMatchObject({ tone: 'dim', extra: '· hidden' });
    expect(chipModel(openOf({ state: 'hidden', reason: 'symbol', showing: 'APUS' }), T0 + 5, 60).lines.join(' ')).toMatch(/shows APUS/);
    expect(chipModel(openOf({ state: 'no_picture' }), T0 + 5, 60)).toMatchObject({ tone: 'bad', extra: 'no picture' });
    expect(chipModel(openOf({ hq: { since: T0, endsAt: T0 + 1800, recording: false, lost: true, error: 'stall', retryAt: null } }), T0 + 5, 60)).toMatchObject({ tone: 'warn', extra: 'lost' });
  });

  it('names every reason a tab is not showing', () => {
    expect(hiddenWords('minimized', null)).toBe('Nova is minimized');
    expect(hiddenWords('page', null)).toBe('the Trader view is not on screen');
    expect(hiddenWords('closed', null)).toBe('its window was closed');
  });
});

describe('videoMenuState', () => {
  const view = readClipsView(wire())!;
  it('locks everything in a browser, and says why', () => {
    const s = videoMenuState({ desktop: false, view: null, symbol: 'PFSA', busy: false });
    expect(s).toMatchObject({ canStart: false, hqLocked: true });
    expect(s.startWhy).toMatch(/desktop app/);
  });

  it('holds High quality at the cap, with the reason on the box', () => {
    const full = readClipsView(wire({ hq_in_use: 2, open: [] }))!;
    const s = videoMenuState({ desktop: true, view: full, symbol: 'APUS', busy: false });
    expect(s).toMatchObject({ canStart: true, hqLocked: true });
    expect(s.hqWhy).toMatch(/Both high-quality captures/);
  });

  it('forces High quality when the screen recording lost the monitor', () => {
    const lost = readClipsView(wire({ open: [], tabs: [{ window_id: 'main', symbol: 'PFSA', visible: true, display_id: 'd1', screen_recording: false }] }))!;
    const s = videoMenuState({ desktop: true, view: lost, symbol: 'PFSA', busy: false });
    expect(s).toMatchObject({ noScreen: true, hqLocked: true, canStart: true });
    expect(s.hqNote).toMatch(/only picture/);
  });

  it('finds the open clip of the symbol', () => {
    expect(videoMenuState({ desktop: true, view, symbol: 'PFSA', busy: false }).open?.clipId).toBe('c1');
  });
});

describe('Records words', () => {
  it('says each status in words', () => {
    expect(statusWords(rowOf({ status: 'exporting', export: { exportId: 'e', state: 'running', file: null, bytes: null, error: null, progress: 0.45, picture: null, blur: [] } })).text).toBe('Exporting 45%');
    expect(statusWords(rowOf({ status: 'failed', export: { exportId: 'e', state: 'failed', file: null, bytes: null, error: 'F: was full', progress: null, picture: null, blur: [] } })).text).toBe('Export failed: F: was full');
    expect(statusWords(rowOf()).text).toBe('Not exported');
  });

  it('says where the frames came from and what the picture shows', () => {
    expect(sourcesWords(rowOf())).toBe('Cut · 15 fps');
    expect(sourcesWords(rowOf({ hqSec: 118 }))).toBe('Mixed: HQ 1:58, cut 1:20');
    expect(sourcesWords(rowOf({ hqSec: 198 }))).toBe('High quality · 30 fps');
    expect(sourcesWords(rowOf({ origin: 'last_n' }))).toBe('Cut (the last 5 min)');
    expect(pictureWords(rowOf({ export: { exportId: 'e', state: 'done', file: 'x', bytes: 1, error: null, progress: null, picture: 'window', blur: [] } }))).toEqual({ text: 'Whole Nova window', warn: 'header in' });
    expect(pictureWords(rowOf({ export: { exportId: 'e', state: 'done', file: 'x', bytes: 1, error: null, progress: null, picture: 'trader_tab', blur: ['plan'] } })).text).toBe('Trader tab · blurred');
  });
});

describe('the export dialog model', () => {
  it('starts from the Trader tab with the private panels blurred and hidden stretches cut', () => {
    expect(defaultSettings(rowOf())).toMatchObject({ startTs: T0, endTs: T0 + 198, picture: 'trader_tab', blur: ['plan', 'ticket', 'orders'], cutHidden: true });
  });

  it('writes the output line and warns past X free accounts', () => {
    const plan = { out: { width: 1200, height: 700, fps: 30, bitrate: 1_764_000 }, duration: 183, counts: { hq_sec: 171, screen_sec: 12, hidden_sec: 15, gap_sec: 0, no_picture_sec: 0 } };
    expect(outputParts(plan)).toEqual(['MP4 (H.264)', '1200 × 700', '30 fps', '3:03 after the cuts', 'up to 38 MB']);
    expect(sourceLine(plan)).toBe('From high quality for 2:51, the screen recording for 0:12.');
    expect(xWarning(183)).toMatch(/Trim 0:43/);
    expect(xWarning(120)).toBeNull();
  });

  it('says what it left out, and that a cut shows whatever covered the tab', () => {
    const plan = { out: { width: 1200, height: 700, fps: 15, bitrate: 900_000 }, duration: 110, counts: { hq_sec: 0, screen_sec: 110, hidden_sec: 0, gap_sec: 0, unknown_sec: 40, no_picture_sec: 0 } };
    expect(outputParts(plan)).toContain('1:50 after the cuts');
    expect(sourceLine(plan)).toBe('From the screen recording for 1:50. 0:40 when Nova was not following the tab is left out.');
    expect(coverLine(plan, 'trader_tab')).toMatch(/a window over the tab is in the cut too/);
    expect(coverLine(plan, 'monitor')).toBeNull();
    expect(coverLine({ ...plan, counts: { ...plan.counts, hq_sec: 110, screen_sec: 0 } }, 'trader_tab')).toBeNull();
  });

  it('scales the timeline, ticks it, and keeps a selection inside it', () => {
    const s = timelineScale(1000, 1100);
    expect(s.pct(1050)).toBe(50);
    expect(s.ts(25)).toBe(1025);
    expect(timelineTicks(T0, T0 + 480).length).toBeGreaterThan(3);
    expect(clampSelection(900, 1200, 1000, 1100)).toEqual({ start: 1000, end: 1100 });
    expect(clampSelection(1099.5, 1099.8, 1000, 1100)).toEqual({ start: 1099, end: 1100 });
  });
});
