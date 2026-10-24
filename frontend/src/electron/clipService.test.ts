/**
 * Share clips' supervisor (ADR 039), driven with fake windows and pages: a
 * clip marks where its tab is and whether it shows, stops on the operator's
 * word, "save the last 5 min" reads the tab's past, a restart marks the gap,
 * High quality starts, writes its file and stops itself at 30 min, the cap
 * holds, and an export runs through the page into a finished MP4.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { startClipService } from '../../electron/clipService.mjs';
import { CLIP_HQ_MAX_SEC } from '../../electron/clipPlan.mjs';
import { CLIP_REC_CMD_CHANNEL, CLIP_REC_CHUNK_CHANNEL, CLIP_REC_EVENT_CHANNEL, CLIP_REC_READY_CHANNEL } from '../../electron/clipHq.mjs';
import { SegmentFile } from '../../electron/screenRecordFiles.mjs';
import {
  CLIP_EXPORT_DONE_CHANNEL,
  CLIP_EXPORT_JOB_CHANNEL,
  CLIP_EXPORT_READ_CHANNEL,
  CLIP_EXPORT_READY_CHANNEL,
  CLIP_EXPORT_WRITE_CHANNEL,
} from '../../electron/clipExporter.mjs';

type Handler = (...args: unknown[]) => unknown;
type Row = Record<string, unknown>;

function emitter() {
  const handlers = new Map<string, Handler[]>();
  return {
    on(name: string, fn: Handler) {
      handlers.set(name, [...(handlers.get(name) ?? []), fn]);
      return this;
    },
    once(name: string, fn: Handler) {
      const wrapped: Handler = (...args) => {
        this.removeListener(name, wrapped);
        return fn(...args);
      };
      return this.on(name, wrapped);
    },
    removeListener(name: string, fn: Handler) {
      handlers.set(name, (handlers.get(name) ?? []).filter((h) => h !== fn));
      return this;
    },
    emit: (name: string, ...args: unknown[]) => [...(handlers.get(name) ?? [])].forEach((h) => h(...args)),
  };
}

let nextId = 1;
class FakeWindow {
  static all: FakeWindow[] = [];
  static getAllWindows = () => FakeWindow.all.filter((w) => !w.destroyed);
  static fromWebContents = (c: { id: number }) => FakeWindow.all.find((w) => w.webContents.id === c.id) ?? null;
  events = emitter();
  sent: { channel: string; msg: Row }[] = [];
  webContents: { id: number; send: (channel: string, msg: Row) => void; on: Handler; getURL: () => string };
  destroyed = false;
  minimized = false;
  loaded: string | null = null;
  constructor(public opts: Row = {}) {
    const id = nextId++;
    this.webContents = { id, send: (channel, msg) => this.sent.push({ channel, msg }), on: () => undefined, getURL: () => 'file:///desk' };
    FakeWindow.all.push(this);
  }
  on(name: string, fn: Handler) { this.events.on(name, fn); return this; }
  once(name: string, fn: Handler) { this.events.once(name, fn); return this; }
  loadFile(p: string) { this.loaded = p; return Promise.resolve(); }
  loadURL(u: string) { this.loaded = u; return Promise.resolve(); }
  isDestroyed() { return this.destroyed; }
  destroy() { this.destroyed = true; }
  isMinimized() { return this.minimized; }
  getContentBounds() { return { x: 0, y: 23, width: 2560, height: 1392 }; }
  getBounds() { return { x: 0, y: 0, width: 2560, height: 1440 }; }
  getMediaSourceId() { return `window:${this.webContents.id}:0`; }
  lastSent(channel: string) { return [...this.sent].reverse().find((s) => s.channel === channel)?.msg ?? null; }
}

function fakeIpc() {
  const e = emitter();
  const handles = new Map<string, Handler>();
  return {
    on: e.on.bind(e),
    removeListener: e.removeListener.bind(e),
    emit: e.emit,
    handle: (name: string, fn: Handler) => { handles.set(name, fn); },
    removeHandler: (name: string) => { handles.delete(name); },
    invoke: (name: string, event: unknown, arg: unknown) => handles.get(name)!(event, arg),
  };
}

const screen = { getDisplayMatching: () => ({ id: 1449598500, scaleFactor: 1 }), getAllDisplays: () => [] };
const DISPLAY = { id: '1449598500', index: 3, count: 3, bounds: { x: 0, y: 0, width: 2560, height: 1440 } };
const tabReport = (over: Row = {}) => ({
  schema_version: 1, window_id: 'main', visible: true, reason: null, symbol: 'PFSA',
  pane: { x: 200, y: 90, w: 1200, h: 700 }, panels: { plan: { x: 1000, y: 120, w: 300, h: 150 } }, inner: { w: 2560, h: 1392 }, ...over,
});

const realImmediate = () => new Promise<void>((resolve) => setImmediate(resolve));
async function settle(rounds = 20) {
  for (let i = 0; i < rounds; i += 1) await realImmediate();
}
async function until(check: () => boolean, rounds = 500) {
  for (let i = 0; i < rounds && !check(); i += 1) await realImmediate();
}
function watch(promise: Promise<unknown>) {
  const state = { settled: false };
  void promise.then(() => { state.settled = true; });
  return state;
}
function holdClose(name?: string) {
  const closeFile = SegmentFile.prototype.close;
  const files: SegmentFile[] = [];
  const held: SegmentFile[] = [];
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const spy = vi.spyOn(SegmentFile.prototype, 'close').mockImplementation(function (this: SegmentFile) {
    const bytes = closeFile.call(this);
    files.push(this);
    if (name && path.basename(this.file) !== name) return bytes;
    held.push(this);
    return bytes.then(async (value) => { await gate; return value; });
  });
  return { files, held, release: () => release(), restore: () => { release(); spy.mockRestore(); } };
}

let tmp: string;
const services: { stop: (r?: string) => Promise<void> | void }[] = [];
beforeEach(() => {
  // setImmediate stays real so file closes finish on their own time (#940).
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(new Date('2026-09-24T12:06:16Z')); // 08:06:16 ET
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-clips-'));
  FakeWindow.all = [];
});
afterEach(async () => {
  await Promise.all(services.splice(0).map((s) => s.stop('quit')));
  vi.useRealTimers();
  fs.rmSync(tmp, { recursive: true, force: true });
});

function world(opts: { screenFiles?: boolean; screenPaused?: boolean } = {}) {
  const ipcMain = fakeIpc();
  const screenDir = path.join(tmp, 'screen');
  let screenView: Row | null = null;
  if (opts.screenFiles !== false) {
    const day = path.join(screenDir, '2026-09-24');
    fs.mkdirSync(day, { recursive: true });
    fs.writeFileSync(path.join(day, '080000-screen3.mkv'), Buffer.alloc(4096, 7));
    fs.writeFileSync(path.join(day, 'segments.jsonl'), `${JSON.stringify({ schema_version: 1, event: 'start', segment_id: 's1', file: '080000-screen3.mkv', display: DISPLAY, width: 2560, height: 1440, fps: 15, started_ts: Date.parse('2026-09-24T12:00:00Z') / 1000 })}\n`);
    screenView = { dir: screenDir, displays: [{ id: DISPLAY.id, recording: true, file: '080000-screen3.mkv' }] };
  }
  // NOVA_SCREEN_RECORD not on (ADR 067): the recorder's paused view, no monitor recorded.
  if (opts.screenPaused) screenView = { state: 'paused', dir: screenDir, displays: [] };
  const views: Row[] = [];
  const shell = { showItemInFolder: vi.fn(), openPath: vi.fn(async () => '') };
  const make = () => {
    const svc = startClipService({
      BrowserWindow: FakeWindow as never,
      screen,
      ipcMain,
      shell,
      userData: tmp,
      env: { NOVA_CLIPS_DIR: path.join(tmp, 'clips') },
      exportPage: { file: 'clip-export.html' },
      screenView: () => screenView,
      onView: (v: Row) => views.push(v),
      logger: { warn: () => undefined, info: () => undefined },
    });
    services.push(svc);
    return svc;
  };
  const rows = (): Row[] => fs.readFileSync(path.join(tmp, 'clips', 'clips.jsonl'), 'utf8').trim().split('\n').map((l) => JSON.parse(l));
  return { ipcMain, make, rows, views, shell, lastView: () => views[views.length - 1] as Row };
}

describe('a cut clip', () => {
  it('marks where the tab is, notices it switch symbol, and stops on the word', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const start = (await svc.act({ action: 'start', symbol: 'PFSA', origin: 'button' })) as Row;
    expect(start).toMatchObject({ ok: true, hq: false, forced: false });
    expect((w.lastView().open as Row[])[0]).toMatchObject({ symbol: 'PFSA', state: 'ok', screen_recording: true, hq: null });
    vi.advanceTimersByTime(20_000);
    svc.tabReport(desk as never, tabReport({ symbol: 'APUS' }));
    expect((w.lastView().open as Row[])[0]).toMatchObject({ state: 'hidden', reason: 'symbol', showing: 'APUS' });
    vi.advanceTimersByTime(10_000);
    svc.tabReport(desk as never, tabReport());
    const stop = (await svc.act({ action: 'stop', clip_id: start.clip_id })) as Row;
    expect(stop).toMatchObject({ ok: true });
    expect(stop.clip).toMatchObject({ status: 'not_exported', length_sec: 30, hidden_sec: 10 });
    const kinds = w.rows().filter((r) => r.clip_id === start.clip_id).map((r) => (r.event === 'mark' ? `mark:${r.kind}` : r.event));
    expect(kinds).toEqual(['open', 'mark:shown', 'mark:geometry', 'mark:hidden', 'mark:shown', 'close']);
  });

  it('refuses a symbol with no tab, and answers a second start with the open clip', async () => {
    const w = world();
    const svc = w.make();
    expect(await svc.act({ action: 'start', symbol: 'ZZZZ' })).toMatchObject({ ok: false, reason: 'CLIP_NO_TAB' });
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const a = (await svc.act({ action: 'start', symbol: 'PFSA' })) as Row;
    expect(await svc.act({ action: 'start', symbol: 'PFSA' })).toMatchObject({ ok: true, clip_id: a.clip_id, already: true });
    expect(await svc.act({ action: 'nope' })).toMatchObject({ ok: false, reason: 'CLIP_INVALID' });
  });

  it('saves the last minutes from where the tab was, and refuses a tab that was not on screen', async () => {
    const w = world();
    const svc = w.make();
    expect(await svc.act({ action: 'save_last', symbol: 'PFSA' })).toMatchObject({ ok: false, reason: 'CLIP_NOT_ON_SCREEN' });
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    vi.advanceTimersByTime(120_000);
    const saved = (await svc.act({ action: 'save_last', symbol: 'PFSA', seconds: 60 })) as Row;
    expect(saved).toMatchObject({ ok: true });
    expect(saved.clip).toMatchObject({ origin: 'last_n', status: 'not_exported', length_sec: 60 });
    const marks = w.rows().filter((r) => r.clip_id === (saved.clip as Row).clip_id && r.event === 'mark');
    expect(marks.map((r) => r.kind)).toEqual(['shown', 'geometry']);
  });

  it('keeps where the tab was before the press, so the export can start earlier; outside that it is not known', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport({ symbol: 'APUS' }));
    const seen = Date.now() / 1000;
    vi.advanceTimersByTime(30_000);
    svc.tabReport(desk as never, tabReport());
    vi.advanceTimersByTime(90_000);
    const start = (await svc.act({ action: 'start', symbol: 'PFSA' })) as Row;
    const t = Date.now() / 1000;
    const before = w.rows().filter((r) => r.clip_id === start.clip_id && r.event === 'mark' && (r.ts as number) < t);
    expect(before.map((r) => [r.kind, (r.ts as number) - seen])).toEqual([['hidden', 0], ['shown', 30], ['geometry', 30]]);
    vi.advanceTimersByTime(10_000);
    await svc.act({ action: 'stop', clip_id: start.clip_id });
    vi.advanceTimersByTime(30_000);
    const d = (await svc.act({ action: 'detail', clip_id: start.clip_id, from_ts: seen - 20, to_ts: t + 30 })) as Row;
    const tl = d.timeline as Row;
    expect(tl.unknown).toEqual([[seen - 20, seen], [t + 10, t + 30]]);
    expect(tl.hidden).toMatchObject([{ start: seen, end: seen + 30, reason: 'not_open' }]);
    expect(tl.shown).toEqual([[seen + 30, t + 10]]);
    // The first marks are stamped at the start itself: nothing between the press and them is unknown.
    const plan = (await svc.act({ action: 'plan', clip_id: start.clip_id, settings: { start_ts: t, end_ts: t + 10 } })) as Row;
    expect((plan.counts as Row).unknown_sec).toBe(0);
  });

  it('keeps an open clip across a restart and marks how long Nova was down', async () => {
    const w = world();
    const first = w.make();
    const desk = new FakeWindow();
    first.tabReport(desk as never, tabReport());
    const a = (await first.act({ action: 'start', symbol: 'PFSA' })) as Row;
    vi.advanceTimersByTime(61_000); // one beat
    first.stop('quit');
    vi.advanceTimersByTime(40_000);
    w.make();
    const restart = w.rows().find((r) => r.clip_id === a.clip_id && r.kind === 'restart') as Row;
    expect(restart).toBeTruthy();
    const detail = restart.detail as Row;
    expect((restart.ts as number) - (detail.down_since as number)).toBeGreaterThanOrEqual(39);
    expect((w.lastView().open as Row[]).map((o) => o.clip_id)).toEqual([a.clip_id]);
  });
});

describe('High quality', () => {
  it('captures the tab window, writes its file, and stops itself at 30 minutes', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const a = (await svc.act({ action: 'start', symbol: 'PFSA', hq: true })) as Row;
    expect(a).toMatchObject({ ok: true, hq: true });
    const page = FakeWindow.all.find((x) => x.opts.title === 'Nova clip recorder')!;
    expect(page).toBeTruthy();
    w.ipcMain.emit(CLIP_REC_READY_CHANNEL, { sender: page.webContents });
    const cmd = page.lastSent(CLIP_REC_CMD_CHANNEL)!;
    expect(cmd).toMatchObject({ cmd: 'start', sourceId: `window:${desk.webContents.id}:0`, fps: 30 });
    w.ipcMain.emit(CLIP_REC_EVENT_CHANNEL, { sender: page.webContents }, { kind: 'started', id: cmd.id, mime: 'video/x-matroska;codecs=avc1' });
    w.ipcMain.emit(CLIP_REC_CHUNK_CHANNEL, { sender: page.webContents }, { id: cmd.id, bytes: new Uint8Array([1, 2, 3]) });
    const start = w.rows().find((r) => r.event === 'hq' && r.state === 'start') as Row;
    expect(start).toMatchObject({ clip_id: a.clip_id, window_id: 'main' });
    expect(String(start.file)).toMatch(/^hq\/2026-09-24\/080616-PFSA-hq\.mkv$/);
    vi.advanceTimersByTime(1_000); // the view is published once a second
    expect((w.lastView().open as Row[])[0].hq).toMatchObject({ recording: true, lost: false });
    // A chunk every second keeps it alive; at 30 minutes it stops and the clip goes on as a cut.
    for (let i = 0; i < CLIP_HQ_MAX_SEC; i += 10) {
      vi.advanceTimersByTime(10_000);
      w.ipcMain.emit(CLIP_REC_CHUNK_CHANNEL, { sender: page.webContents }, { id: cmd.id, bytes: null });
    }
    expect(w.rows().some((r) => r.event === 'set' && r.hq === false && r.reason === 'limit')).toBe(true);
    expect(page.lastSent(CLIP_REC_CMD_CHANNEL)).toMatchObject({ cmd: 'stop', id: cmd.id });
    w.ipcMain.emit(CLIP_REC_EVENT_CHANNEL, { sender: page.webContents }, { kind: 'stopped', id: cmd.id });
    await vi.waitFor(() => expect(w.rows().some((r) => r.event === 'hq' && r.state === 'end' && r.reason === 'limit')).toBe(true));
    vi.advanceTimersByTime(1_000);
    expect((w.lastView().open as Row[])[0]).toMatchObject({ clip_id: a.clip_id, hq: null });
  });

  it('holds at two captures, and records in high quality when the screen recording lost the monitor', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const other = new FakeWindow();
    svc.tabReport(other as never, tabReport({ window_id: 'trader:APUS', symbol: 'APUS' }));
    const third = new FakeWindow();
    svc.tabReport(third as never, tabReport({ window_id: 'trader:NVDA', symbol: 'NVDA' }));
    expect(await svc.act({ action: 'start', symbol: 'PFSA', hq: true })).toMatchObject({ ok: true });
    expect(await svc.act({ action: 'start', symbol: 'APUS', hq: true })).toMatchObject({ ok: true });
    expect(await svc.act({ action: 'start', symbol: 'NVDA', hq: true })).toMatchObject({ ok: false, reason: 'CLIP_HQ_FULL' });
    expect(await svc.act({ action: 'start', symbol: 'NVDA' })).toMatchObject({ ok: true, hq: false });
    expect(w.lastView()).toMatchObject({ hq_in_use: 2, hq_max: 2 });
  });

  it('is the picture while the screen recording is paused, and Save the last 5 min says why it cannot run (ADR 067)', async () => {
    const w = world({ screenFiles: false, screenPaused: true });
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const other = new FakeWindow();
    svc.tabReport(other as never, tabReport({ window_id: 'trader:APUS', symbol: 'APUS' }));
    const third = new FakeWindow();
    svc.tabReport(third as never, tabReport({ window_id: 'trader:NVDA', symbol: 'NVDA' }));
    vi.advanceTimersByTime(120_000);
    expect(await svc.act({ action: 'save_last', symbol: 'PFSA', seconds: 60 })).toMatchObject({
      ok: false, reason: 'CLIP_NO_PICTURE', error: expect.stringMatching(/^Screen recording is paused \(off by default\)/),
    });
    expect(await svc.act({ action: 'start', symbol: 'PFSA' })).toMatchObject({ ok: true, hq: true, forced: true });
    expect(await svc.act({ action: 'start', symbol: 'APUS' })).toMatchObject({ ok: true, hq: true, forced: true });
    expect(await svc.act({ action: 'start', symbol: 'NVDA' })).toMatchObject({
      ok: false, reason: 'CLIP_NO_PICTURE', error: 'Screen recording is paused, and both high-quality captures are in use: stop one first.',
    });
    vi.advanceTimersByTime(1_000);
    expect(w.lastView()).toMatchObject({ screen_paused: true, hq_in_use: 2 });
    expect((w.lastView().tabs as Row[]).map((t) => t.screen_recording)).toEqual([false, false, false]);
  });

  it('writes the quit end row synchronously, awaits active file close, and returns the same completion on repeated stop (#940)', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const a = (await svc.act({ action: 'start', symbol: 'PFSA', hq: true })) as Row;
    const page = FakeWindow.all.find((x) => x.opts.title === 'Nova clip recorder')!;
    w.ipcMain.emit(CLIP_REC_READY_CHANNEL, { sender: page.webContents });
    const cmd = page.lastSent(CLIP_REC_CMD_CHANNEL)!;
    w.ipcMain.emit(CLIP_REC_EVENT_CHANNEL, { sender: page.webContents }, { kind: 'started', id: cmd.id, mime: 'video/x-matroska;codecs=avc1' });
    w.ipcMain.emit(CLIP_REC_CHUNK_CHANNEL, { sender: page.webContents }, { id: cmd.id, bytes: new Uint8Array([1, 2, 3, 4, 5]) });
    const hold = holdClose('080616-PFSA-hq.mkv');
    try {
      const stop = svc.stop('quit') as Promise<void>;
      expect(stop).toBeInstanceOf(Promise);
      expect(svc.stop('quit')).toBe(stop);
      const stopped = watch(stop);
      expect(page.lastSent(CLIP_REC_CMD_CHANNEL)).toMatchObject({ cmd: 'stop', id: cmd.id });
      expect(page.isDestroyed()).toBe(true);
      expect(w.rows().some((r) => r.event === 'close')).toBe(false);
      const ends = () => w.rows().filter((r) => r.event === 'hq' && r.state === 'end');
      expect(ends()).toEqual([
        { schema_version: 1, ts: 1790251576, event: 'hq', clip_id: a.clip_id, state: 'end', file: 'hq/2026-09-24/080616-PFSA-hq.mkv', reason: 'quit', error: null },
      ]);
      await until(() => hold.files.length === 1 && hold.files[0].stream.closed);
      await settle();
      expect(stopped.settled).toBe(false);
      hold.release();
      await stop;
      expect(stopped.settled).toBe(true);
      expect(hold.files[0].stream.closed).toBe(true);
      expect(await svc.stop('quit')).toBeUndefined();
      expect(ends()).toHaveLength(1);
    } finally {
      hold.restore();
    }
  });

  it('awaits an already-running HQ finalizer across stop, preserves its error attribution, and writes nothing after folder removal (#940)', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const other = new FakeWindow();
    svc.tabReport(other as never, tabReport({ window_id: 'trader:APUS', symbol: 'APUS' }));
    const pfsa = (await svc.act({ action: 'start', symbol: 'PFSA', hq: true })) as Row;
    const apus = (await svc.act({ action: 'start', symbol: 'APUS', hq: true })) as Row;
    const page = FakeWindow.all.find((x) => x.opts.title === 'Nova clip recorder')!;
    w.ipcMain.emit(CLIP_REC_READY_CHANNEL, { sender: page.webContents });
    const starts = page.sent.filter((s) => s.channel === CLIP_REC_CMD_CHANNEL && s.msg.cmd === 'start').map((s) => s.msg);
    expect(starts).toHaveLength(2);
    for (const s of starts) {
      w.ipcMain.emit(CLIP_REC_EVENT_CHANNEL, { sender: page.webContents }, { kind: 'started', id: s.id, mime: 'video/x-matroska;codecs=avc1' });
      w.ipcMain.emit(CLIP_REC_CHUNK_CHANNEL, { sender: page.webContents }, { id: s.id, bytes: new Uint8Array([7, 8, 9]) });
    }
    const hold = holdClose('080616-PFSA-hq.mkv');
    try {
      w.ipcMain.emit(CLIP_REC_EVENT_CHANNEL, { sender: page.webContents }, { kind: 'stopped', id: starts[0].id, message: 'encoder stalled' });
      expect(hold.held).toHaveLength(1);
      const stop = svc.stop('quit') as Promise<void>;
      expect(stop).toBeInstanceOf(Promise);
      expect(svc.stop('quit')).toBe(stop);
      const stopped = watch(stop);
      const ends = () => w.rows().filter((r) => r.event === 'hq' && r.state === 'end');
      expect(ends().map((r) => [r.clip_id, r.reason, r.error])).toEqual([[apus.clip_id, 'quit', null]]);
      await until(() => hold.files.length === 2 && hold.files.every((f) => f.stream.closed));
      await settle();
      expect(stopped.settled).toBe(false);
      hold.release();
      await stop;
      expect(hold.files.every((f) => f.stream.closed)).toBe(true);
      expect(ends().map((r) => [r.clip_id, r.reason, r.error])).toEqual([
        [apus.clip_id, 'quit', null],
        [pfsa.clip_id, 'error', 'encoder stalled'],
      ]);
      const clipsDir = path.join(tmp, 'clips');
      fs.rmSync(clipsDir, { recursive: true, force: true });
      await settle(50);
      expect(fs.existsSync(clipsDir)).toBe(false);
    } finally {
      hold.restore();
    }
  });
});

describe('export', () => {
  it('runs a stopped clip through the page into a finished MP4', async () => {
    const w = world();
    const svc = w.make();
    const desk = new FakeWindow();
    svc.tabReport(desk as never, tabReport());
    const a = (await svc.act({ action: 'start', symbol: 'PFSA' })) as Row;
    vi.advanceTimersByTime(30_000);
    await svc.act({ action: 'stop', clip_id: a.clip_id });
    expect(await svc.act({ action: 'export', clip_id: 'nope' })).toMatchObject({ ok: false, reason: 'CLIP_UNKNOWN' });
    const ex = (await svc.act({ action: 'export', clip_id: a.clip_id, settings: { blur: ['plan'] } })) as Row;
    expect(ex).toMatchObject({ ok: true, out: { width: 1200, height: 700, fps: 15 }, duration: 30 });
    const page = FakeWindow.all.find((x) => x.opts.title === 'Nova clip export')!;
    w.ipcMain.emit(CLIP_EXPORT_READY_CHANNEL, { sender: page.webContents });
    await vi.waitFor(() => expect(page.lastSent(CLIP_EXPORT_JOB_CHANNEL)).toBeTruthy());
    const job = page.lastSent(CLIP_EXPORT_JOB_CHANNEL)!;
    const piece = (job.pieces as Row[])[0];
    expect(piece).toMatchObject({ kind: 'screen', t0: 376, t1: 406, out0: 0, crop: { x: 200, y: 113, w: 1200, h: 700 } });
    // The page reads by token only and writes the MP4 through the main process.
    const bytes = (await w.ipcMain.invoke(CLIP_EXPORT_READ_CHANNEL, { sender: page.webContents }, { token: piece.token, start: 0, end: 16 })) as Uint8Array;
    expect(bytes.length).toBe(16);
    await expect(w.ipcMain.invoke(CLIP_EXPORT_READ_CHANNEL, { sender: desk.webContents }, { token: piece.token, start: 0, end: 16 })).rejects.toThrow();
    await w.ipcMain.invoke(CLIP_EXPORT_WRITE_CHANNEL, { sender: page.webContents }, { job_id: job.job_id, position: 0, data: new Uint8Array([9, 9, 9]) });
    w.ipcMain.emit(CLIP_EXPORT_DONE_CHANNEL, { sender: page.webContents }, { job_id: job.job_id, ok: true });
    await vi.waitFor(() => expect(fs.existsSync(String(ex.file))).toBe(true));
    vi.advanceTimersByTime(1_000);
    const row = (w.lastView().clips as Row[]).find((c) => c.clip_id === a.clip_id)!;
    expect(row).toMatchObject({ status: 'ready', export: { state: 'done', bytes: 3 } });
    expect(await svc.act({ action: 'show', clip_id: a.clip_id })).toMatchObject({ ok: true });
    expect(w.shell.showItemInFolder).toHaveBeenCalledWith(String(ex.file));
    // Delete takes the export, never the screen recording.
    expect(await svc.act({ action: 'delete', clip_id: a.clip_id })).toMatchObject({ ok: true, files: 1 });
    expect(fs.existsSync(String(ex.file))).toBe(false);
    expect(fs.existsSync(path.join(tmp, 'screen', '2026-09-24', '080000-screen3.mkv'))).toBe(true);
  });

  it('closes open export and source handles before stop settles (#940)', async () => {
    const openHandle = fs.promises.open;
    let releaseHandles!: () => void;
    const gate = new Promise<void>((resolve) => { releaseHandles = resolve; });
    const closedHandles: string[] = [];
    const spy = vi.spyOn(fs.promises, 'open').mockImplementation(async (...args) => {
      const handle = await openHandle(...args);
      const realClose = handle.close.bind(handle);
      handle.close = async () => {
        await realClose();
        await gate;
        closedHandles.push(path.basename(String(args[0])));
      };
      return handle;
    });
    try {
      const w = world();
      const svc = w.make();
      const desk = new FakeWindow();
      svc.tabReport(desk as never, tabReport());
      const a = (await svc.act({ action: 'start', symbol: 'PFSA' })) as Row;
      vi.advanceTimersByTime(30_000);
      await svc.act({ action: 'stop', clip_id: a.clip_id });
      const ex = (await svc.act({ action: 'export', clip_id: a.clip_id })) as Row;
      const page = FakeWindow.all.find((x) => x.opts.title === 'Nova clip export')!;
      w.ipcMain.emit(CLIP_EXPORT_READY_CHANNEL, { sender: page.webContents });
      await vi.waitFor(() => expect(page.lastSent(CLIP_EXPORT_JOB_CHANNEL)).toBeTruthy());
      const job = page.lastSent(CLIP_EXPORT_JOB_CHANNEL)!;
      const piece = (job.pieces as Row[])[0];
      await w.ipcMain.invoke(CLIP_EXPORT_READ_CHANNEL, { sender: page.webContents }, { token: piece.token, start: 0, end: 16 });
      await w.ipcMain.invoke(CLIP_EXPORT_WRITE_CHANNEL, { sender: page.webContents }, { job_id: job.job_id, position: 0, data: new Uint8Array([1, 2, 3]) });
      const stop = svc.stop('quit') as Promise<void>;
      const stopped = watch(stop);
      const failed = w.rows().filter((r) => r.event === 'export' && r.state === 'failed');
      expect(failed).toHaveLength(1);
      expect(failed[0]).toMatchObject({ clip_id: a.clip_id, error: 'Nova quit while exporting' });
      await settle();
      expect(stopped.settled).toBe(false);
      releaseHandles();
      await stop;
      expect(closedHandles).toHaveLength(2);
      expect(fs.existsSync(`${String(ex.file)}.part`)).toBe(false);
    } finally {
      releaseHandles();
      spy.mockRestore();
    }
  });
});
