/**
 * The graphics card's safety net (operator decision 2026-10-05, #707): software from the next start when
 * the graphics process stops, and a restart in software when the window goes blank -- three blank checks
 * in a row while the operator is at the PC, never on one picture alone.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readChoice } from '../../electron/graphicsChoice.mjs';
import {
  GRAPHICS_BLANK_CHECKS,
  GRAPHICS_LOADED_GRACE_MS,
  createScreenSampler,
  fractionRect,
  startGraphicsWatch,
  uniformShare,
} from '../../electron/graphicsWatch.mjs';

type Handler = (...args: unknown[]) => void;
type Picture = { data: Uint8Array; width: number; height: number };

/** A `width` x `height` picture of one colour. */
function flat(width: number, height: number, rgb = [11, 15, 20]): Picture {
  const data = new Uint8Array(width * height * 4);
  for (let i = 0; i < width * height; i += 1) data.set([...rgb, 255], i * 4);
  return { data, width, height };
}

/** A picture with content: a different colour every few pixels, as a desk page has. */
function busy(width: number, height: number): Picture {
  const data = new Uint8Array(width * height * 4);
  for (let i = 0; i < width * height; i += 1) data.set([(i * 37) % 256, (i * 91) % 256, (i * 13) % 256, 255], i * 4);
  return { data, width, height };
}

function image(p: Picture | null) {
  return {
    isEmpty: () => p === null,
    resize: () => image(p),
    getSize: () => ({ width: p?.width ?? 0, height: p?.height ?? 0 }),
    toBitmap: () => p?.data ?? new Uint8Array(0),
  };
}

describe('uniformShare', () => {
  it('is the share of pixels near the median colour', () => {
    expect(uniformShare(flat(10, 10).data, 10, 10)).toBe(1);
    const half = flat(10, 10);
    half.data.fill(200, 0, 200); // the first 50 pixels white
    expect(uniformShare(half.data, 10, 10)).toBe(0.5);
    expect(uniformShare(busy(96, 54).data, 96, 54)).toBeLessThan(0.05);
  });

  it('says nothing for a picture shorter than its size', () => {
    expect(uniformShare(new Uint8Array(8), 10, 10)).toBeNull();
  });
});

describe('fractionRect', () => {
  const display = { x: -2560, y: -509, width: 2560, height: 1441 };

  it('places a window on its monitor as fractions', () => {
    expect(fractionRect({ x: -2560, y: -509, width: 1280, height: 1441 }, display)).toEqual({ x: 0, y: 0, w: 0.5, h: 1 });
  });

  it('keeps the part on the monitor, and nothing off it', () => {
    expect(fractionRect({ x: -1280, y: -509, width: 2560, height: 1441 }, display)).toEqual({ x: 0.5, y: 0, w: 0.5, h: 1 });
    expect(fractionRect({ x: 10, y: 10, width: 100, height: 100 }, display)).toBeNull();
  });
});

describe('createScreenSampler', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('matches an answer to its request', async () => {
    const sent: unknown[][] = [];
    const sampler = createScreenSampler({ request: (...args: unknown[]) => { sent.push(args); return true; } });
    const got = sampler.sample('7', { x: 0, y: 0, w: 1, h: 1 });
    expect(sent[0]).toEqual(['7', { x: 0, y: 0, w: 1, h: 1 }, 1, { width: 96, height: 54 }]);
    sampler.answer({ reqId: 99, width: 1, height: 1, data: new Uint8Array(4) }); // someone else's
    sampler.answer({ reqId: 1, width: 1, height: 1, data: new Uint8Array(4) });
    await expect(got).resolves.toEqual({ data: new Uint8Array(4), width: 1, height: 1 });
  });

  it('answers null when the monitor is not recording, the page errs or nothing comes back', async () => {
    const no = createScreenSampler({ request: () => false });
    await expect(no.sample('7', {})).resolves.toBeNull();
    const yes = createScreenSampler({ request: () => true, timeoutMs: 1000 });
    const erred = yes.sample('7', {});
    yes.answer({ reqId: 1, error: 'that monitor has no live capture' });
    await expect(erred).resolves.toBeNull();
    const silent = yes.sample('7', {});
    await vi.advanceTimersByTimeAsync(1000);
    await expect(silent).resolves.toBeNull();
  });
});

describe('startGraphicsWatch', () => {
  let dir = '';
  let t = 0;
  let screenShot: Picture | null = null;
  let pageShot: Picture | null = null;
  let idle = 'active';
  let focused: ReturnType<typeof makeWindow> | null = null;
  const handlers = new Map<string, Handler[]>();
  const app = {
    on: (name: string, fn: Handler) => handlers.set(name, [...(handlers.get(name) ?? []), fn]),
    removeListener: (name: string, fn: Handler) => handlers.set(name, (handlers.get(name) ?? []).filter((h) => h !== fn)),
    emit: (name: string, ...args: unknown[]) => (handlers.get(name) ?? []).forEach((h) => h(...args)),
  };
  const fallbacks: { reason: string; detail: string }[] = [];
  const logger = { warn: vi.fn(), error: vi.fn() };
  let watch: ReturnType<typeof startGraphicsWatch>;

  function makeWindow() {
    return {
      minimized: false,
      isDestroyed: () => false,
      isMinimized() { return this.minimized; },
      isVisible: () => true,
      getContentBounds: () => ({ x: 0, y: 0, width: 1920, height: 1080 }),
      webContents: { isLoading: () => false, capturePage: async () => image(pageShot), invalidate: vi.fn() },
    };
  }

  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nova-gwatch-'));
    t = 1_000_000;
    screenShot = flat(96, 54);
    pageShot = busy(96, 54);
    idle = 'active';
    focused = makeWindow();
    fallbacks.length = 0;
    handlers.clear();
    watch = startGraphicsWatch({
      app,
      BrowserWindow: { getFocusedWindow: () => focused },
      screen: { getDisplayMatching: () => ({ id: 7, bounds: { x: 0, y: 0, width: 1920, height: 1080 } }) },
      powerMonitor: { getSystemIdleState: () => idle },
      sampler: { sample: async () => screenShot },
      isDeskWindow: () => true,
      userData: dir,
      onFallback: ({ reason, detail }: { reason: string; detail: string }) => fallbacks.push({ reason, detail }),
      logger,
      now: () => t,
      timers: { setInterval: () => 0, clearInterval: () => {}, setTimeout: (fn: () => void, ms: number) => setTimeout(fn, ms), clearTimeout: (id: number) => clearTimeout(id) },
    });
  });
  afterEach(() => {
    watch.stop();
    fs.rmSync(dir, { recursive: true, force: true });
  });

  /** A check after the window has stood loaded through the grace. */
  async function settledCheck() {
    await watch.check(); // first sight of the loaded window starts its grace
    t += GRAPHICS_LOADED_GRACE_MS;
    await watch.check();
  }

  it('restarts in software after three blank checks in a row, and asks the window to draw first', async () => {
    await settledCheck();
    expect(watch.streak()).toBe(1);
    expect(focused?.webContents.invalidate).toHaveBeenCalledOnce();
    for (let i = 1; i < GRAPHICS_BLANK_CHECKS; i += 1) await watch.check();
    expect(fallbacks).toEqual([{ reason: 'blank_window', detail: 'the window showed one flat colour for 15 s while the page drew content' }]);
    expect(readChoice(dir).choice).toMatchObject({ gpu: 'off', reason: 'blank_window', told: false });
    await watch.check();
    expect(fallbacks).toHaveLength(1); // once
  });

  it('leaves a freshly loaded window alone', async () => {
    await watch.check();
    expect(watch.streak()).toBe(0);
  });

  it('starts over when a check sees the screen draw again', async () => {
    await settledCheck();
    await watch.check();
    expect(watch.streak()).toBe(2);
    screenShot = busy(96, 54);
    await watch.check();
    expect(watch.streak()).toBe(0);
    expect(fallbacks).toEqual([]);
  });

  it('decides nothing while the page itself draws one colour (it is loading)', async () => {
    pageShot = flat(96, 54);
    await settledCheck();
    expect(watch.streak()).toBe(0);
  });

  it('decides nothing while the operator is away, the window is minimised, or no picture comes back', async () => {
    idle = 'idle';
    await settledCheck();
    expect(watch.streak()).toBe(0);
    idle = 'active';
    if (focused) focused.minimized = true;
    await watch.check();
    expect(watch.streak()).toBe(0);
    if (focused) focused.minimized = false;
    screenShot = null;
    await watch.check();
    expect(watch.streak()).toBe(0);
    expect(fallbacks).toEqual([]);
  });

  it('turns the graphics card off for the next start when its process crashes, and only then', async () => {
    app.emit('child-process-gone', {}, { type: 'Utility', reason: 'crashed' });
    app.emit('child-process-gone', {}, { type: 'GPU', reason: 'killed' });
    expect(fallbacks).toEqual([]);
    app.emit('child-process-gone', {}, { type: 'GPU', reason: 'crashed', exitCode: -1073741819 });
    expect(fallbacks).toEqual([{ reason: 'gpu_crashed', detail: 'the graphics process crashed (exit code -1073741819)' }]);
    expect(readChoice(dir).choice).toMatchObject({ gpu: 'off', reason: 'gpu_crashed' });
  });
});
