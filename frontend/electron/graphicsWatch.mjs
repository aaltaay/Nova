/**
 * The graphics card's safety net (operator decision 2026-10-05: draw with the graphics card, and fall back
 * to software by itself "if the GPU process fails or the window goes black"). Two signals:
 *
 * - **The graphics process ends abnormally** (`child-process-gone`, type `GPU`). Chromium starts it again
 *   and the desk keeps drawing, so nothing restarts: the next start draws in software, and main.mjs tells
 *   the operator now.
 * - **The window goes blank**: the screen under the focused desk window shows one flat colour while the
 *   page itself draws content (2026-09-17 had a black client area under a live page). The screen is read
 *   from the trading screen recording's own capture of that monitor (ADR 035): asking Windows for a screen
 *   picture took 0.9-1.6 s a call on the desk PC, while a patch of the recorder's live frame costs its page
 *   a few milliseconds. The page is read (`capturePage`, ~0.1 s for a 4K window) only once the screen looks
 *   blank. The first blank check asks the window to draw again; three in a row, 5 s apart, while the
 *   operator is at the PC, store "software" and hand over to main.mjs, which restarts Nova.
 *
 * Nothing is decided without both pictures: no recording of that monitor, no answer in time, a page that
 * is itself one colour (loading), a minimised or unfocused window, or an operator away from the PC each
 * leave the window alone. Electron, the clock and the timers are passed in, so this is testable without it.
 */
import { writeChoice } from './graphicsChoice.mjs';

export const GRAPHICS_CHECK_MS = 5_000;
export const GRAPHICS_BLANK_CHECKS = 3;
/** A screen patch this uniform is blank: a healthy Trader page measured 8-18% near its median colour, the Scanner 55%. */
export const GRAPHICS_BLANK_SHARE = 0.97;
/** A page this uniform draws nothing to compare with (it is loading): no decision. */
export const GRAPHICS_PAGE_CONTENT_MAX_SHARE = 0.9;
/** Only while the operator is at the PC: input within this many seconds. */
export const GRAPHICS_ACTIVE_SEC = 15;
/** A window that just finished loading is left alone this long. */
export const GRAPHICS_LOADED_GRACE_MS = 20_000;
export const GRAPHICS_SAMPLE_W = 96;
export const GRAPHICS_SAMPLE_H = 54;
export const GRAPHICS_SAMPLE_TIMEOUT_MS = 3_000;
export const GRAPHICS_PAGE_TIMEOUT_MS = 3_000;
/** How far a channel may sit from the median and still be the same colour. */
const UNIFORM_TOL = 6;
/** How a graphics process ends that counts as a failure (not a clean exit, not killed on quit). */
const GPU_GONE = new Set(['crashed', 'oom', 'launch-failed', 'abnormal-exit', 'integrity-failure']);

const errText = (err) => (err instanceof Error ? err.message : String(err));

/** The share of pixels within a few levels of the median colour; 4 bytes a pixel in any channel order, alpha ignored. */
export function uniformShare(data, width, height) {
  const n = width * height;
  if (!data || n <= 0 || data.length < n * 4) return null;
  const hist = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  for (let i = 0; i < n; i += 1) {
    for (let c = 0; c < 3; c += 1) hist[c][data[i * 4 + c]] += 1;
  }
  const median = hist.map((h) => {
    let acc = 0;
    for (let v = 0; v < 256; v += 1) {
      acc += h[v];
      if (acc * 2 >= n) return v;
    }
    return 255;
  });
  let near = 0;
  for (let i = 0; i < n; i += 1) {
    if (
      Math.abs(data[i * 4] - median[0]) <= UNIFORM_TOL
      && Math.abs(data[i * 4 + 1] - median[1]) <= UNIFORM_TOL
      && Math.abs(data[i * 4 + 2] - median[2]) <= UNIFORM_TOL
    ) near += 1;
  }
  return near / n;
}

/** `bounds` as fractions of `display` (both in DIPs), clipped to it; null when they do not overlap. */
export function fractionRect(bounds, display) {
  if (!bounds || !display || display.width <= 0 || display.height <= 0) return null;
  const left = Math.max(bounds.x, display.x);
  const top = Math.max(bounds.y, display.y);
  const right = Math.min(bounds.x + bounds.width, display.x + display.width);
  const bottom = Math.min(bounds.y + bounds.height, display.y + display.height);
  if (right <= left || bottom <= top) return null;
  return {
    x: (left - display.x) / display.width,
    y: (top - display.y) / display.height,
    w: (right - left) / display.width,
    h: (bottom - top) / display.height,
  };
}

/**
 * Small screen pictures from the screen recorder's page, matched to their requests. `request(displayId,
 * rect, reqId, size)` asks the recorder and returns false when that monitor has no capture; the page's
 * answer comes back through `answer`. A picture is `{data, width, height}` (RGBA), else null.
 */
export function createScreenSampler({ request, timers = globalThis, timeoutMs = GRAPHICS_SAMPLE_TIMEOUT_MS }) {
  const pending = new Map();
  let seq = 0;
  return {
    sample(displayId, rect) {
      return new Promise((resolve) => {
        seq += 1;
        const reqId = seq;
        let sent = false;
        try {
          sent = request(displayId, rect, reqId, { width: GRAPHICS_SAMPLE_W, height: GRAPHICS_SAMPLE_H });
        } catch {
          sent = false;
        }
        if (!sent) {
          resolve(null);
          return;
        }
        const timer = timers.setTimeout(() => {
          pending.delete(reqId);
          resolve(null);
        }, timeoutMs);
        pending.set(reqId, (ev) => {
          timers.clearTimeout(timer);
          const ok = !ev.error && ev.data && ev.width > 0 && ev.height > 0;
          resolve(ok ? { data: ev.data, width: ev.width, height: ev.height } : null);
        });
      });
    },
    answer(ev) {
      const done = pending.get(ev?.reqId);
      if (!done) return;
      pending.delete(ev.reqId);
      done(ev);
    },
  };
}

function withTimeout(promise, ms, timers) {
  return new Promise((resolve) => {
    const timer = timers.setTimeout(() => resolve(null), ms);
    Promise.resolve(promise).then(
      (v) => {
        timers.clearTimeout(timer);
        resolve(v);
      },
      () => {
        timers.clearTimeout(timer);
        resolve(null);
      },
    );
  });
}

/**
 * Watch a desk that draws with the graphics card. `onFallback({reason, detail, choice})` runs once, after
 * "software" is stored: main.mjs tells the operator (a crash) or restarts Nova (a blank window).
 */
export function startGraphicsWatch({
  app,
  BrowserWindow,
  screen,
  powerMonitor,
  sampler,
  isDeskWindow,
  userData,
  onFallback,
  logger = console,
  now = () => Date.now(),
  timers = globalThis,
  intervalMs = GRAPHICS_CHECK_MS,
}) {
  let done = false;
  let busy = false;
  let streak = 0;
  const loadedSince = new WeakMap();

  function fallBack(reason, detail) {
    if (done) return;
    done = true;
    timers.clearInterval(interval);
    const choice = { gpu: 'off', reason, at: Math.round(now() / 1000), detail, told: false };
    try {
      writeChoice(userData, choice);
    } catch (err) {
      logger.error(`[nova] graphics: could not store "software" (${errText(err)})`);
    }
    logger.warn(`[nova] graphics: ${detail}; drawing in software from now on`);
    onFallback({ reason, detail, choice });
  }

  function onGone(_event, details) {
    if (details?.type !== 'GPU' || !GPU_GONE.has(String(details.reason))) return;
    fallBack('gpu_crashed', `the graphics process ${details.reason} (exit code ${details.exitCode ?? 'unknown'})`);
  }

  /** The window the operator is looking at, once it has stood loaded through the grace; else null. */
  function watchedWindow() {
    const w = BrowserWindow.getFocusedWindow?.();
    if (!w || w.isDestroyed() || !isDeskWindow(w) || w.isMinimized() || !w.isVisible()) return null;
    const wc = w.webContents;
    if (wc.isLoading()) {
      loadedSince.delete(wc);
      return null;
    }
    if (!loadedSince.has(wc)) loadedSince.set(wc, now());
    return now() - loadedSince.get(wc) >= GRAPHICS_LOADED_GRACE_MS ? w : null;
  }

  /** One look: true blank, false not blank, null no decision. */
  async function looksBlank(w) {
    if (powerMonitor?.getSystemIdleState?.(GRAPHICS_ACTIVE_SEC) !== 'active') return null;
    const bounds = w.getContentBounds();
    const display = screen.getDisplayMatching(bounds);
    const rect = fractionRect(bounds, display?.bounds);
    if (!rect) return null;
    const shot = await sampler.sample(display.id, rect);
    const screenShare = shot ? uniformShare(shot.data, shot.width, shot.height) : null;
    if (screenShare === null) return null;
    if (screenShare < GRAPHICS_BLANK_SHARE) return false;
    const page = await withTimeout(w.webContents.capturePage(), GRAPHICS_PAGE_TIMEOUT_MS, timers);
    if (page && !page.isEmpty?.()) {
      const small = page.resize({ width: GRAPHICS_SAMPLE_W });
      const size = small.getSize();
      const pageShare = uniformShare(small.toBitmap(), size.width, size.height);
      // The page itself draws nothing (loading, an empty route): the screen agrees with it.
      if (pageShare === null || pageShare > GRAPHICS_PAGE_CONTENT_MAX_SHARE) return null;
    }
    // The page drew content, or could not even hand over a picture: the screen shows none of it.
    return true;
  }

  async function check() {
    if (done || busy) return;
    busy = true;
    try {
      const w = watchedWindow();
      const blank = w ? await looksBlank(w) : null;
      if (done) return;
      if (blank !== true) {
        streak = 0; // in a row means in a row: a look that decides nothing starts over
        return;
      }
      streak += 1;
      logger.warn(`[nova] graphics: the focused window looks blank (${streak}/${GRAPHICS_BLANK_CHECKS})`);
      if (streak === 1) w.webContents.invalidate?.();
      if (streak >= GRAPHICS_BLANK_CHECKS) {
        fallBack('blank_window', `the window showed one flat colour for ${Math.round((streak * intervalMs) / 1000)} s while the page drew content`);
      }
    } catch (err) {
      logger.warn(`[nova] graphics: check failed (${errText(err)})`);
    } finally {
      busy = false;
    }
  }

  app.on('child-process-gone', onGone);
  const interval = timers.setInterval(() => void check(), intervalMs);
  interval?.unref?.();

  return {
    check,
    streak: () => streak,
    stop() {
      done = true;
      timers.clearInterval(interval);
      app.removeListener?.('child-process-gone', onGone);
    },
  };
}
