import { describe, expect, it } from 'vitest';
import {
  initialView,
  parseRunning,
  pendingSummary,
  runningFromHtml,
  withDisconnect,
  withFolded,
  withHeldUpdate,
  withServerBack,
  withServerCode,
  type CodeState,
  type RunningCode,
} from './holdModel';

const running: RunningCode = { boot: 'b1', seq: 2, head: 'aaa1111' };

const disk = (over: Partial<CodeState> = {}): CodeState => ({
  schema_version: 1,
  boot: 'b1',
  seq: 2,
  head: 'aaa1111',
  at: '2026-10-27T14:00:00.000Z',
  recent: [
    { seq: 2, kind: 'source', file: 'src/old.ts' },
    { seq: 1, kind: 'source', file: 'src/older.ts' },
  ],
  ...over,
});

describe('parseRunning / runningFromHtml', () => {
  it('reads the revision the page was served with', () => {
    expect(parseRunning('b1.2', 'aaa1111')).toEqual(running);
    expect(parseRunning('b1.2', '')).toEqual({ boot: 'b1', seq: 2, head: null });
    expect(parseRunning('', 'x')).toBeNull();
    expect(parseRunning('nonsense', null)).toBeNull();
  });

  it('reads it from a fetched page too (the dev server once it is back)', () => {
    const html = '<head><meta charset="UTF-8" /><meta name="nova-dev-code" content="zz.0" data-head="bbb2222"></head>';
    expect(runningFromHtml(html)).toEqual({ boot: 'zz', seq: 0, head: 'bbb2222' });
    expect(runningFromHtml('<head></head>')).toBeNull();
  });
});

describe('pendingSummary', () => {
  it('nothing is pending while the page runs the code on disk', () => {
    expect(pendingSummary(initialView(running))).toBeNull();
    expect(pendingSummary(withServerCode(initialView(running), disk()))).toBeNull();
  });

  it('counts and names only the changes after this page loaded', () => {
    const code = disk({
      seq: 6,
      head: 'bbb2222',
      recent: [
        { seq: 6, kind: 'source', file: 'src/a.ts' },
        { seq: 5, kind: 'reload', file: null },
        { seq: 4, kind: 'source', file: 'src/b.ts' },
        { seq: 3, kind: 'html', file: 'index.html' },
        { seq: 2, kind: 'source', file: 'src/c.ts' },
      ],
    });
    // A later announcement with the same seq is the same code (e.g. a hello reply).
    const view = withServerCode(initialView(running), code);
    expect(pendingSummary(view)).toEqual({
      changes: 4,
      restarted: false,
      server: 'up',
      files: ['src/a.ts', 'src/b.ts', 'index.html'],
      moreFiles: 0,
      runningHead: 'aaa1111',
      diskHead: 'bbb2222',
    });
  });

  it('lists three files and counts the rest', () => {
    const recent = [7, 6, 5, 4, 3].map((seq) => ({ seq, kind: 'source' as const, file: `src/f${seq}.ts` }));
    const s = pendingSummary(withServerCode(initialView(running), disk({ seq: 7, recent })));
    expect(s?.files).toEqual(['src/f7.ts', 'src/f6.ts', 'src/f5.ts']);
    expect(s?.moreFiles).toBe(2);
  });

  it('a different boot means the dev server restarted: it counts afresh', () => {
    const s = pendingSummary(withServerCode(initialView(running), disk({ boot: 'b2', seq: 1, recent: [] })));
    expect(s).toMatchObject({ restarted: true, changes: null, files: [] });
  });

  it('a lost socket is pending even with no change, and says so until the server is back', () => {
    const down = withDisconnect(initialView(running));
    expect(pendingSummary(down)).toMatchObject({ server: 'down', restarted: true });
    const back = withServerBack(down, { boot: 'b2', seq: 0, head: 'ccc3333' });
    expect(pendingSummary(back)).toMatchObject({ server: 'back', restarted: true, diskHead: 'ccc3333' });
    expect(pendingSummary(withServerBack(down, null))).toMatchObject({ server: 'back' });
  });

  it("the page's own guard catching a Vite reload is pending", () => {
    expect(pendingSummary(withHeldUpdate(initialView(running)))).toMatchObject({ restarted: false, changes: null });
  });

  it('ignores an announcement of another shape', () => {
    const view = initialView(running);
    expect(withServerCode(view, { schema_version: 2, boot: 'x', seq: 9, recent: [] })).toBe(view);
    expect(withServerCode(view, 'nope')).toBe(view);
  });

  it('Later folds; anything new unfolds the notice again only for a stop or a held reload', () => {
    const folded = withFolded(withServerCode(initialView(running), disk({ seq: 3 })), true);
    expect(folded.folded).toBe(true);
    expect(pendingSummary(folded)).not.toBeNull(); // folded is still pending, never applied
    expect(withServerCode(folded, disk({ seq: 4 })).folded).toBe(true);
    expect(withDisconnect(folded).folded).toBe(false);
    // A server that flaps after it came back does not pop a folded notice open each time.
    const backFolded = withFolded(withServerBack(withDisconnect(folded), null), true);
    expect(withDisconnect(backFolded).folded).toBe(true);
    expect(withServerBack(backFolded, null)).toBe(backFolded);
    expect(withHeldUpdate(folded).folded).toBe(false);
  });
});
