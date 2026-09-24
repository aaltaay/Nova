/**
 * The trading screen recording's supervisor (ADR 035; operator: "I always,
 * always, always want the screen that I'm trading to be recorded"). Driven
 * with a fake recorder page: every monitor starts, rotation never leaves a
 * gap, a stall / crash / failed start is resumed with backoff and said, a
 * display change re-plans, and quitting closes every file.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SCREEN_REC_CHUNK_CHANNEL,
  SCREEN_REC_CMD_CHANNEL,
  SCREEN_REC_EVENT_CHANNEL,
  SCREEN_REC_READY_CHANNEL,
  startScreenRecorder,
} from '../../electron/screenRecorder.mjs';
import { SCREEN_RECORD_STALL_MS } from '../../electron/screenRecordPlan.mjs';

type Handler = (...args: unknown[]) => void;
type Cmd = { cmd: string; id: string; sourceId?: string; width?: number };
type Row = Record<string, unknown>;

function emitter() {
  const handlers = new Map<string, Handler[]>();
  return {
    on: (name: string, fn: Handler) => {
      handlers.set(name, [...(handlers.get(name) ?? []), fn]);
    },
    once(name: string, fn: Handler) {
      const wrapped: Handler = (...args) => {
        this.removeListener(name, wrapped);
        fn(...args);
      };
      this.on(name, wrapped);
    },
    removeListener: (name: string, fn: Handler) => {
      handlers.set(name, (handlers.get(name) ?? []).filter((h) => h !== fn));
    },
    emit: (name: string, ...args: unknown[]) => [...(handlers.get(name) ?? [])].forEach((h) => h(...args)),
    count: (name: string) => (handlers.get(name) ?? []).length,
  };
}

const MIME = 'video/x-matroska;codecs=avc1';
const LEFT = { id: 11, label: 'left', bounds: { x: -2560, y: 0, width: 2560, height: 1440 }, size: { width: 2560, height: 1440 }, scaleFactor: 1.5 };
const MAIN = { id: 22, label: 'main', bounds: { x: 0, y: 0, width: 1920, height: 1080 }, size: { width: 1920, height: 1080 }, scaleFactor: 1 };

const worlds: { recorder: { stop: (reason?: string) => void } }[] = [];

function makeWorld(tmp: string, opts: { env?: Record<string, string> } = {}) {
  const pages: FakePage[] = [];
  const ipcMain = emitter();
  let displays = [LEFT, MAIN];
  const screen = { ...emitter(), getAllDisplays: () => displays, getPrimaryDisplay: () => MAIN };
  const desktopCapturer = {
    getSources: vi.fn(async () => displays.map((d) => ({ id: `screen:${d.id}:0`, display_id: String(d.id) }))),
  };
  const powerMonitor = emitter();

  class FakePage {
    events = emitter();
    destroyed = false;
    commands: Cmd[] = [];
    webContents = {
      ...emitter(),
      send: (channel: string, cmd: Cmd) => {
        if (channel === SCREEN_REC_CMD_CHANNEL) this.commands.push(cmd);
      },
    };
    constructor() {
      pages.push(this);
    }
    on(name: string, fn: Handler) {
      this.events.on(name, fn);
    }
    loadFile() {
      return Promise.resolve();
    }
    isDestroyed() {
      return this.destroyed;
    }
    destroy() {
      this.destroyed = true;
      this.events.emit('closed');
    }
  }

  const views: Row[] = [];
  const recorder = startScreenRecorder({
    BrowserWindow: FakePage,
    desktopCapturer,
    screen,
    powerMonitor,
    ipcMain,
    userData: path.join(tmp, 'userdata'),
    env: opts.env ?? { NOVA_SCREEN_RECORD_DIR: path.join(tmp, 'rec') },
    onView: (v: Row) => views.push(v),
    logger: { info: () => {}, warn: () => {} },
    segmentMs: 60_000,
  });

  worlds.push({ recorder });
  const page = () => pages[pages.length - 1];
  const from = (p = page()) => ({ sender: p.webContents });
  const live = new Set<string>(); // started segments the fake page keeps feeding
  const event = (ev: Row, p = page()) => {
    if (ev.kind === 'started') live.add(String(ev.id));
    if (ev.kind === 'stopped') live.delete(String(ev.id));
    ipcMain.emit(SCREEN_REC_EVENT_CHANNEL, from(p), ev);
  };
  const chunk = (id: string, bytes: Uint8Array | null, p = page()) =>
    ipcMain.emit(SCREEN_REC_CHUNK_CHANNEL, from(p), { id, bytes });
  /** Time passes while every running capture sends its (still-screen) data, as the real page does. */
  const run = async (ms: number, { silent = [] as string[] } = {}) => {
    for (let t = 0; t < ms; t += 1_000) {
      const stopped = new Set(page().commands.filter((c) => c.cmd === 'stop').map((c) => c.id));
      for (const id of live) if (!stopped.has(id) && !silent.includes(id)) chunk(id, null);
      await vi.advanceTimersByTimeAsync(Math.min(1_000, ms - t));
    }
  };
  return {
    recorder,
    pages,
    page,
    views,
    view: () => recorder.view(),
    screen,
    powerMonitor,
    ipcMain,
    setDisplays: (next: typeof displays) => {
      displays = next;
    },
    ready: (p = page()) => ipcMain.emit(SCREEN_REC_READY_CHANNEL, from(p)),
    event,
    chunk,
    run,
    starts: (p = page()) => p.commands.filter((c) => c.cmd === 'start'),
    stops: (p = page()) => p.commands.filter((c) => c.cmd === 'stop'),
  };
}

const realImmediate = () => new Promise<void>((resolve) => setImmediate(resolve));
async function settle(rounds = 20) {
  for (let i = 0; i < rounds; i += 1) await realImmediate();
}

/** Waits (on real I/O, not the fake clock) until the check passes; file closes finish on their own time. */
async function until(check: () => boolean, rounds = 500) {
  for (let i = 0; i < rounds && !check(); i += 1) await realImmediate();
}

function manifest(dir: string): Row[] {
  const out: Row[] = [];
  if (!fs.existsSync(dir)) return out;
  for (const day of fs.readdirSync(dir)) {
    const file = path.join(dir, day, 'segments.jsonl');
    if (!fs.existsSync(file)) continue;
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) if (line.trim()) out.push(JSON.parse(line));
  }
  return out;
}

let tmp = '';
beforeEach(() => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-screen-'));
  // setImmediate stays real so file writes can finish between steps.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
  vi.setSystemTime(Date.UTC(2026, 8, 24, 13, 44, 0)); // 09:44:00 ET
});
afterEach(async () => {
  // Every recorder stops and its files close before the folder goes: Windows will not delete an open file.
  for (const w of worlds.splice(0)) w.recorder.stop('quit');
  await settle(50);
  vi.useRealTimers();
  fs.rmSync(tmp, { recursive: true, force: true, maxRetries: 10, retryDelay: 50 });
});

async function recordingWorld(env?: Record<string, string>) {
  const w = makeWorld(tmp, { env });
  w.ready();
  await settle();
  for (const s of w.starts()) w.event({ kind: 'started', id: s.id, mime: MIME, width: s.width, height: 1440 });
  await settle();
  return w;
}

describe('startScreenRecorder', () => {
  it('records every monitor once the recorder page is ready, and says so', async () => {
    const w = makeWorld(tmp);
    expect(w.view().state).toBe('starting');
    w.ready();
    await settle();
    const starts = w.starts();
    expect(starts.map((s) => s.sourceId)).toEqual(['screen:11:0', 'screen:22:0']);
    for (const s of starts) w.event({ kind: 'started', id: s.id, mime: MIME });
    w.chunk(starts[0].id, new Uint8Array([1, 2, 3]));
    await settle();
    const v = w.view() as Row & { displays: Row[] };
    expect(v.state).toBe('recording');
    expect(v.recording).toBe(true);
    expect(v.mime).toBe(MIME);
    expect(v.displays.map((d) => [d.index, d.recording, d.file])).toEqual([
      [1, true, '094400-screen1.mkv'],
      [2, true, '094400-screen2.mkv'],
    ]);
    const rows = manifest(path.join(tmp, 'rec'));
    expect(rows.filter((r) => r.event === 'start').map((r) => r.file)).toEqual(['094400-screen1.mkv', '094400-screen2.mkv']);
    expect(rows[0]).toMatchObject({ schema_version: 1, fps: 15, mime: MIME });
  });

  it('starts the next file before stopping the old one, so a rotation leaves no gap', async () => {
    const w = await recordingWorld();
    const first = w.starts().map((s) => s.id);
    w.chunk(first[0], new Uint8Array(10));
    await w.run(60_000); // the 09:45 boundary
    await settle();
    const next = w.starts().slice(2);
    expect(next).toHaveLength(2);
    expect(w.stops()).toHaveLength(0); // the old files keep going until the new ones run
    for (const s of next) w.event({ kind: 'started', id: s.id, mime: MIME });
    expect(w.stops().map((s) => s.id)).toEqual(first);
    for (const id of first) w.event({ kind: 'stopped', id });
    await until(() => manifest(path.join(tmp, 'rec')).filter((r) => r.event === 'end').length === 2);
    const ends = manifest(path.join(tmp, 'rec')).filter((r) => r.event === 'end');
    expect(ends.map((r) => [r.file, r.reason])).toEqual([
      ['094400-screen1.mkv', 'rotation'],
      ['094400-screen2.mkv', 'rotation'],
    ]);
    expect(ends[0].bytes).toBe(10);
    expect(w.view().state).toBe('recording');
    expect((w.view() as { problems: unknown[] }).problems).toEqual([]);
  });

  it('keeps the old file going when the next one fails to start', async () => {
    const w = await recordingWorld();
    await w.run(60_000);
    await settle();
    const [a] = w.starts().slice(2);
    w.event({ kind: 'error', id: a.id, message: 'NotReadableError: Could not start video source' });
    expect(w.stops()).toHaveLength(0);
    expect(w.view().state).toBe('recording');
  });

  it('starts a stalled monitor again and says so', async () => {
    const w = await recordingWorld();
    const [a, b] = w.starts();
    // Monitor 2 keeps sending data (a still screen still sends a frame a second); monitor 1 goes silent.
    await w.run(SCREEN_RECORD_STALL_MS + 3_000, { silent: [a.id] });
    expect(w.stops().map((s) => s.id)).not.toContain(b.id);
    expect(w.stops().map((s) => s.id)).toEqual([a.id]);
    const v = w.view() as Row & { problems: Row[]; displays: Row[] };
    expect(v.state).toBe('partial');
    expect(v.problems[0]).toMatchObject({ display_index: 1, reason: 'stall', resumed_at: null });
    await w.run(3_000); // the first retry wait, then the next watch
    const retry = w.starts().slice(2);
    expect(retry.map((s) => s.sourceId)).toEqual(['screen:11:0']);
    w.event({ kind: 'started', id: retry[0].id, mime: MIME });
    const after = w.view() as Row & { problems: Row[] };
    expect(after.state).toBe('recording');
    expect(after.problems[0].resumed_at).not.toBeNull();
  });

  it('never gives up on a monitor that will not start', async () => {
    const w = makeWorld(tmp);
    w.ready();
    await settle();
    // Ten minutes of every start failing at once (a capture Windows will not give).
    let answered = 0;
    for (let t = 0; t < 600_000; t += 1_000) {
      for (const s of w.starts().slice(answered)) {
        w.event({ kind: 'error', id: s.id, message: 'NotReadableError: Could not start video source' });
        answered += 1;
      }
      await vi.advanceTimersByTimeAsync(1_000);
    }
    // 2 + 5 + 10 + 30 s, then every 60 s: about a dozen tries a monitor, and still trying.
    expect(answered).toBeGreaterThanOrEqual(2 * 12);
    const v = w.view() as Row & { displays: Row[]; problems: Row[] };
    expect(v.displays[0].retry_at).not.toBeNull();
    expect(v.state).toBe('failed');
    expect(v.error).toMatch(/Could not start video source/);
    expect(v.displays[0].error).toMatch(/Could not start/);
    expect(v.problems).toHaveLength(2); // said once per monitor, not once per retry
  });

  it('replaces a crashed recorder page and records again', async () => {
    const w = await recordingWorld();
    const crashed = w.page();
    crashed.webContents.emit('render-process-gone', {}, { reason: 'crashed' });
    await settle();
    let v = w.view() as Row & { problems: Row[] };
    expect(v.state).toBe('failed');
    expect(v.error).toMatch(/recorder process ended \(crashed\)/);
    expect(v.problems.map((p) => p.reason)).toEqual(['recorder_gone', 'recorder_gone']);
    expect(crashed.destroyed).toBe(true);
    await vi.advanceTimersByTimeAsync(6_000);
    expect(w.pages).toHaveLength(2);
    w.ready();
    await settle();
    for (const s of w.starts()) w.event({ kind: 'started', id: s.id, mime: MIME });
    v = w.view() as Row & { problems: Row[] };
    expect(v.state).toBe('recording');
    expect(v.problems.every((p) => p.resumed_at !== null)).toBe(true);
    const endsOf = () => manifest(path.join(tmp, 'rec')).filter((r) => r.event === 'end');
    await until(() => endsOf().length === 2);
    expect(endsOf().map((r) => r.reason)).toEqual(['recorder_gone', 'recorder_gone']);
  });

  it('ignores chunks and events from any window but its own recorder', async () => {
    const w = await recordingWorld();
    const [a] = w.starts();
    const desk = { webContents: {} };
    w.ipcMain.emit(SCREEN_REC_EVENT_CHANNEL, { sender: desk.webContents }, { kind: 'stopped', id: a.id });
    w.ipcMain.emit(SCREEN_REC_CHUNK_CHANNEL, { sender: desk.webContents }, { id: a.id, bytes: new Uint8Array(5) });
    expect(w.view().state).toBe('recording');
    expect((w.view() as { displays: Row[] }).displays[0].bytes).toBe(0);
  });

  it('re-plans when a monitor goes away, without calling it a problem', async () => {
    const w = await recordingWorld();
    const [a] = w.starts();
    w.setDisplays([MAIN]);
    w.screen.emit('display-removed');
    await vi.advanceTimersByTimeAsync(2_500);
    await settle();
    expect(w.stops().map((s) => s.id)).toEqual([a.id]);
    const v = w.view() as Row & { displays: Row[]; problems: Row[] };
    expect(v.displays.map((d) => d.id)).toEqual(['22']);
    expect(v.state).toBe('recording');
    expect(v.problems).toEqual([]);
  });

  it('says so when a capture ends by itself, and starts it again', async () => {
    const w = await recordingWorld();
    const [a] = w.starts();
    w.event({ kind: 'stopped', id: a.id });
    await settle();
    const v = w.view() as Row & { problems: Row[] };
    expect(v.state).toBe('partial');
    expect(v.problems[0]).toMatchObject({ display_index: 1, reason: 'error' });
    await w.run(6_000);
    await settle();
    expect(w.starts().slice(2).map((s) => s.sourceId)).toEqual(['screen:11:0']);
  });

  it('pauses for sleep and records again on wake', async () => {
    const w = await recordingWorld();
    w.powerMonitor.emit('suspend');
    expect(w.view().state).toBe('suspended');
    expect(w.stops()).toHaveLength(2);
    w.powerMonitor.emit('resume');
    await settle();
    expect(w.starts()).toHaveLength(4);
  });

  it('closes every file on quit and lets go of every listener', async () => {
    const w = await recordingWorld();
    const [a] = w.starts();
    w.chunk(a.id, new Uint8Array(7));
    w.recorder.stop('quit');
    await settle();
    const v = w.view() as Row & { displays: Row[] };
    expect(v.state).toBe('stopped');
    expect(v.displays.every((d) => d.recording === false)).toBe(true);
    const ends = manifest(path.join(tmp, 'rec')).filter((r) => r.event === 'end');
    expect(ends.map((r) => [r.reason, r.bytes])).toEqual([['quit', 7], ['quit', 0]]);
    expect(w.ipcMain.count(SCREEN_REC_EVENT_CHANNEL)).toBe(0);
    expect(w.screen.count('display-removed')).toBe(0);
  });

  it('records to the app folder, and says why, when the chosen folder cannot be written', async () => {
    const blocker = path.join(tmp, 'not-a-folder');
    fs.writeFileSync(blocker, 'x');
    const w = await recordingWorld({ NOVA_SCREEN_RECORD_DIR: path.join(blocker, 'rec') });
    const v = w.view() as Row;
    expect(v.dir).toBe(path.join(tmp, 'userdata', 'screen'));
    expect(v.dir_source).toBe('fallback');
    expect(v.dir_note).toMatch(/cannot be written/);
    expect(v.state).toBe('recording');
  });
});
