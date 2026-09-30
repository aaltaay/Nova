/**
 * Share clips' export plan (ADR 039): a clip's stretch becomes pieces --
 * high quality where it ran in the tab's window, the screen recording
 * everywhere else, so a lost capture leaves no hole -- with hidden stretches
 * cut on request, restart gaps left out, and the blur boxes in the crop.
 */
import { describe, expect, it } from 'vitest';
import { foldRows } from '../../electron/clipManifest.mjs';
import { buildExportPlan, clipTimeline } from '../../electron/clipExportPlan.mjs';

const V = 1;
const DISPLAY = { id: 'd3', index: 3, bounds: { x: 0, y: 0, width: 2560, height: 1440 } };
const GEO = {
  window_id: 'main',
  display_id: 'd3',
  content: { x: 0, y: 23, width: 2560, height: 1392 },
  inner: { w: 2560, h: 1392 },
  pane: { x: 200, y: 90, w: 1200, h: 700 },
  panels: { plan: { x: 1000, y: 120, w: 300, h: 150 } },
};
// Two quarter-hour screen segments, the second starting at t = 1000.
const SEGS = [
  { file: 'F:/screen/a.mkv', startedTs: 100, endedTs: 1000, display: DISPLAY, width: 2560, height: 1440 },
  { file: 'F:/screen/b.mkv', startedTs: 1000, endedTs: 1900, display: DISPLAY, width: 2560, height: 1440 },
];

function clipWith(extra: Record<string, unknown>[] = []) {
  const { clips } = foldRows([
    { schema_version: V, event: 'open', clip_id: 'c', ts: 950, started_ts: 950, symbol: 'PFSA', hq: false },
    { schema_version: V, event: 'mark', clip_id: 'c', ts: 950, kind: 'shown', detail: { window_id: 'main' } },
    { schema_version: V, event: 'mark', clip_id: 'c', ts: 950, kind: 'geometry', detail: GEO },
    ...extra,
    { schema_version: V, event: 'close', clip_id: 'c', ts: 1060, ended_ts: 1060 },
  ]);
  const c = clips.get('c');
  return { ...c, hq: c.hq.map((s: { file: string }) => ({ ...s, file: `F:/clips/${s.file}` })) };
}
const settings = (over: Record<string, unknown> = {}) => ({ start_ts: 950, end_ts: 1060, picture: 'trader_tab', panels: [], blur: [], cut_hidden: true, ...over });

describe('buildExportPlan', () => {
  it('cuts across a quarter-hour rotation into two pieces of the tab', () => {
    const plan = buildExportPlan({ clip: clipWith(), settings: settings(), screenSegments: SEGS, now: 5000 });
    expect(plan.out).toMatchObject({ width: 1200, height: 700, fps: 15 });
    expect(plan.pieces).toEqual([
      { kind: 'screen', file: 'F:/screen/a.mkv', t0: 850, t1: 900, out0: 0, crop: { x: 200, y: 113, w: 1200, h: 700 }, blur: [], window: null },
      { kind: 'screen', file: 'F:/screen/b.mkv', t0: 0, t1: 60, out0: 50, crop: { x: 200, y: 113, w: 1200, h: 700 }, blur: [], window: null },
    ]);
    expect(plan.duration).toBe(110);
  });

  it('takes high quality where it ran and the screen recording around it', () => {
    const clip = clipWith([
      { schema_version: V, event: 'hq', clip_id: 'c', ts: 960, state: 'start', file: 'hq/h.mkv', window_id: 'main' },
      { schema_version: V, event: 'hq', clip_id: 'c', ts: 990, state: 'end', file: 'hq/h.mkv', reason: 'error' },
    ]);
    const plan = buildExportPlan({ clip, settings: settings({ blur: ['plan'] }), screenSegments: SEGS, now: 5000 });
    expect(plan.out.fps).toBe(30);
    expect(plan.pieces.map((p: { kind: string; t0: number; t1: number; out0: number }) => [p.kind, p.t0, p.t1, p.out0])).toEqual([
      ['screen', 850, 860, 0],
      ['hq', 0, 30, 10],
      ['screen', 890, 900, 40],
      ['screen', 0, 60, 50],
    ]);
    const hq = plan.pieces[1];
    expect(hq.crop).toBeNull();
    expect(hq.window).toEqual({
      dip: { x: 200, y: 90, w: 1200, h: 700 },
      content: { width: 2560, height: 1392 },
      blur: [{ x: 1000, y: 120, w: 300, h: 150 }],
    });
    // The screen pieces blur the plan card where it sits in their crop.
    expect(plan.pieces[0].blur).toEqual([{ x: 800, y: 30, w: 300, h: 150 }]);
    expect(plan.counts).toMatchObject({ hq_sec: 30, screen_sec: 80 });
  });

  it('cuts a hidden stretch when asked, and keeps it when not', () => {
    const clip = clipWith([
      { schema_version: V, event: 'mark', clip_id: 'c', ts: 1010, kind: 'hidden', detail: { reason: 'symbol', showing: 'APUS' } },
      { schema_version: V, event: 'mark', clip_id: 'c', ts: 1025, kind: 'shown', detail: { window_id: 'main' } },
    ]);
    const cut = buildExportPlan({ clip, settings: settings(), screenSegments: SEGS, now: 5000 });
    expect(cut.duration).toBe(95);
    expect(cut.counts.hidden_sec).toBe(15);
    const kept = buildExportPlan({ clip, settings: settings({ cut_hidden: false }), screenSegments: SEGS, now: 5000 });
    expect(kept.duration).toBe(110);
  });

  it('leaves out the time Nova was down', () => {
    const clip = clipWith([{ schema_version: V, event: 'mark', clip_id: 'c', ts: 1030, kind: 'restart', detail: { down_since: 1000 } }]);
    const plan = buildExportPlan({ clip, settings: settings(), screenSegments: SEGS, now: 5000 });
    expect(plan.counts.gap_sec).toBe(30);
    expect(plan.duration).toBe(80);
  });

  it('says so when nothing has a picture', () => {
    const plan = buildExportPlan({ clip: clipWith(), settings: settings(), screenSegments: [], now: 5000 });
    expect(plan.error).toMatch(/nothing/);
    expect(plan.counts.no_picture_sec).toBe(110);
    expect(buildExportPlan({ clip: clipWith(), settings: settings({ end_ts: 900 }), screenSegments: SEGS, now: 5000 }).error).toMatch(/empty/);
  });

  it('leaves out what Nova did not follow -- before the first mark, after the stop -- and says so', () => {
    const wide = settings({ start_ts: 930, end_ts: 1080 });
    const plan = buildExportPlan({ clip: clipWith(), settings: wide, screenSegments: SEGS, now: 5000 });
    expect(plan.counts.unknown_sec).toBe(40);
    expect(plan.duration).toBe(110);
    // Keeping hidden stretches does not bring it back: where the tab was is not known.
    const kept = buildExportPlan({ clip: clipWith(), settings: { ...wide, cut_hidden: false }, screenSegments: SEGS, now: 5000 });
    expect(kept.duration).toBe(110);
    const before = buildExportPlan({ clip: clipWith(), settings: settings({ start_ts: 900, end_ts: 940 }), screenSegments: SEGS, now: 5000 });
    expect(before.error).toMatch(/not following the tab/);
  });

  it('can export the whole monitor from the screen recording', () => {
    const plan = buildExportPlan({ clip: clipWith(), settings: settings({ picture: 'monitor' }), screenSegments: SEGS, now: 5000 });
    expect(plan.pieces[0].crop).toEqual({ x: 0, y: 0, w: 2560, h: 1440 });
    expect(plan.out).toMatchObject({ width: 1920, height: 1080 });
  });
});

describe('clipTimeline', () => {
  it('draws the tracks the export dialog shows', () => {
    const clip = clipWith([
      { schema_version: V, event: 'hq', clip_id: 'c', ts: 960, state: 'start', file: 'hq/h.mkv', window_id: 'main' },
      { schema_version: V, event: 'hq', clip_id: 'c', ts: 990, state: 'end', file: 'hq/h.mkv', reason: 'operator' },
      { schema_version: V, event: 'mark', clip_id: 'c', ts: 1010, kind: 'hidden', detail: { reason: 'symbol', showing: 'APUS' } },
      { schema_version: V, event: 'mark', clip_id: 'c', ts: 1025, kind: 'shown', detail: { window_id: 'main' } },
    ]);
    const t = clipTimeline({ clip, screenSegments: SEGS, from: 940, to: 1070, now: 5000 });
    expect(t.hq).toEqual([[960, 990]]);
    expect(t.hidden).toEqual([{ start: 1010, end: 1025, showing: 'APUS', reason: 'symbol' }]);
    expect(t.screen).toEqual([[940, 1070]]);
    expect(t.shown).toEqual([[950, 1010], [1025, 1060]]);
    expect(t.unknown).toEqual([[940, 950], [1060, 1070]]);
  });
});
