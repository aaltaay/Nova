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

let tmp: string;
let services: { stop: (r?: string) => void }[] = [];
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-09-24T12:06:16Z')); // 08:06:16 ET
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-clips-'));
  FakeWindow.all = [];
});
afterEach(() => {
  for (const s of services) s.stop('quit');
  services = [];
  vi.useRealTimers();
  fs.rmSync(tmp, { recursive: true, force: true });
});

function world(opts: { screenFiles?: boolean } = {}) {
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
});
