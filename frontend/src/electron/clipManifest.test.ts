/**
 * Share clips' manifest (ADR 039), folded: a clip's rows become its state, a
 * row it cannot read is counted and never guessed, and the spans the export
 * and the chips read come out of the marks.
 */
import { describe, expect, it } from 'vitest';
import {
  applyRow,
  clipRow,
  clipStatus,
  foldRows,
  geometryAt,
  isOpen,
  parseManifest,
  restartGaps,
  visibilitySpans,
} from '../../electron/clipManifest.mjs';

const V = 1;
const G1 = { window_id: 'main', display_id: 'd', content: { x: 0, y: 0, width: 100, height: 100 }, inner: { w: 100, h: 100 }, pane: { x: 0, y: 0, w: 50, h: 50 }, panels: {} };
const G2 = { ...G1, pane: { x: 10, y: 10, w: 50, h: 50 } };

function rows() {
  return [
    { schema_version: V, event: 'open', clip_id: 'c1', ts: 100, started_ts: 100, symbol: 'PFSA', origin: 'button', picture: 'trader_tab', hq: true },
    { schema_version: V, event: 'mark', clip_id: 'c1', ts: 100, kind: 'shown', detail: { window_id: 'main' } },
    { schema_version: V, event: 'mark', clip_id: 'c1', ts: 100, kind: 'geometry', detail: G1 },
    { schema_version: V, event: 'hq', clip_id: 'c1', ts: 101, state: 'start', file: 'hq/a.mkv', window_id: 'main' },
    { schema_version: V, event: 'mark', clip_id: 'c1', ts: 130, kind: 'hidden', detail: { reason: 'symbol', showing: 'APUS' } },
    { schema_version: V, event: 'mark', clip_id: 'c1', ts: 145, kind: 'shown', detail: { window_id: 'main' } },
    { schema_version: V, event: 'mark', clip_id: 'c1', ts: 150, kind: 'geometry', detail: G2 },
    { schema_version: V, event: 'hq', clip_id: 'c1', ts: 170, state: 'end', file: 'hq/a.mkv', reason: 'error', error: 'stall' },
    { schema_version: V, event: 'beat', ts: 160, clip_ids: ['c1'] },
    { schema_version: V, event: 'close', clip_id: 'c1', ts: 200, ended_ts: 200, reason: 'operator' },
  ];
}

describe('foldRows', () => {
  it('folds a clip from open to close, with its high-quality file and marks', () => {
    const { clips, skipped } = foldRows(rows());
    expect(skipped).toBe(0);
    const c = clips.get('c1');
    expect(c.symbol).toBe('PFSA');
    expect(c.startedTs).toBe(100);
    expect(c.endedTs).toBe(200);
    expect(isOpen(c)).toBe(false);
    expect(c.hq).toEqual([{ start: 101, end: 170, file: 'hq/a.mkv', windowId: 'main', reason: 'error', error: 'stall' }]);
    expect(c.marks.map((m: { kind: string }) => m.kind)).toEqual(['shown', 'geometry', 'hidden', 'shown', 'geometry']);
  });

  it('counts a row of another version, an unknown event or an unknown clip, and keeps going', () => {
    const { clips, skipped } = foldRows([
      { schema_version: 2, event: 'open', clip_id: 'x', ts: 1, symbol: 'A' },
      { schema_version: V, event: 'wat', clip_id: 'c1', ts: 1 },
      { schema_version: V, event: 'close', clip_id: 'nope', ts: 1 },
      ...rows(),
    ]);
    expect(skipped).toBe(3);
    expect(clips.size).toBe(1);
  });

  it('parses the file line by line and counts a line that is not JSON', () => {
    const { rows: parsed, bad } = parseManifest('{"a":1}\n{broken\n\n{"b":2}\n');
    expect(parsed).toEqual([{ a: 1 }, { b: 2 }]);
    expect(bad).toBe(1);
  });
});

describe('spans', () => {
  const c = foldRows(rows()).clips.get('c1');

  it('says when the tab showed and why not', () => {
    expect(visibilitySpans(c, 100, 200)).toEqual([
      { start: 100, end: 130, shown: true, reason: null, showing: null },
      { start: 130, end: 145, shown: false, reason: 'symbol', showing: 'APUS' },
      { start: 145, end: 200, shown: true, reason: null, showing: null },
    ]);
  });

  it('never takes the tab to be shown where Nova did not follow it: before the first mark, after the stop', () => {
    expect(visibilitySpans(c, 80, 220)).toEqual([
      { start: 80, end: 100, shown: false, reason: 'unknown', showing: null },
      { start: 100, end: 130, shown: true, reason: null, showing: null },
      { start: 130, end: 145, shown: false, reason: 'symbol', showing: 'APUS' },
      { start: 145, end: 200, shown: true, reason: null, showing: null },
      { start: 200, end: 220, shown: false, reason: 'unknown', showing: null },
    ]);
    // A clip still recording follows its tab up to now.
    const open = foldRows(rows().slice(0, 9)).clips.get('c1');
    expect(visibilitySpans(open, 190, 220)).toEqual([{ start: 190, end: 220, shown: true, reason: null, showing: null }]);
  });

  it('reads the geometry of a moment, else the first one', () => {
    expect(geometryAt(c, 120)).toEqual(G1);
    expect(geometryAt(c, 160)).toEqual(G2);
    expect(geometryAt(c, 50)).toEqual(G1);
  });

  it('turns a restart mark into the gap Nova was down', () => {
    const clips = foldRows(rows().slice(0, 9)).clips;
    applyRow(clips, { schema_version: V, event: 'mark', clip_id: 'c1', ts: 400, kind: 'restart', detail: { down_since: 160 } });
    expect(restartGaps(clips.get('c1'))).toEqual([{ start: 160, end: 400 }]);
  });
});

describe('status and the row', () => {
  it('follows a clip from recording to ready', () => {
    const clips = foldRows(rows().slice(0, 9)).clips;
    const c = clips.get('c1');
    expect(clipStatus(c)).toBe('recording');
    applyRow(clips, { schema_version: V, event: 'close', clip_id: 'c1', ts: 200, ended_ts: 200 });
    expect(clipStatus(c)).toBe('not_exported');
    applyRow(clips, { schema_version: V, event: 'export', clip_id: 'c1', ts: 201, export_id: 'e1', state: 'queued', file: '2026-09-24/PFSA-080616.mp4' });
    expect(clipStatus(c)).toBe('queued');
    applyRow(clips, { schema_version: V, event: 'export', clip_id: 'c1', ts: 202, export_id: 'e1', state: 'running' });
    expect(clipStatus(c)).toBe('exporting');
    applyRow(clips, { schema_version: V, event: 'export', clip_id: 'c1', ts: 230, export_id: 'e1', state: 'done', bytes: 38_000_000 });
    expect(clipStatus(c)).toBe('ready');
    const row = clipRow(c, 300);
    expect(row).toMatchObject({ clip_id: 'c1', length_sec: 100, status: 'ready', hq_sec: 69, hidden_sec: 15, gap_sec: 0 });
    expect(row.export).toMatchObject({ export_id: 'e1', state: 'done', file: '2026-09-24/PFSA-080616.mp4', bytes: 38_000_000 });
  });
});
