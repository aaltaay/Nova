/**
 * Share clips (ADR 039), the pure half: the numbers, where clips live, what
 * their files are called, and how a Trader tab's rectangle maps into a frame
 * of the screen recording (ADR 035) or of a high-quality window capture. No
 * electron or node imports, so it is testable as is.
 *
 * A rectangle the page reports is in CSS pixels, relative to the window's
 * page (the content area). `content` is that area on the screen in DIP
 * (Electron's getContentBounds) and `inner` its size in CSS pixels
 * (innerWidth x innerHeight), so a page zoom never skews the crop.
 */

export const CLIP_SCHEMA_VERSION = 1;
/** At most this many high-quality captures at once (operator decision 2026-09-29). */
export const CLIP_HQ_MAX_CONCURRENT = 2;
/** A high-quality capture stops itself after this long; the clip goes on as a cut. */
export const CLIP_HQ_MAX_SEC = 30 * 60;
/** The chip counts down the capture's last minute. */
export const CLIP_HQ_WARN_SEC = 60;
export const CLIP_HQ_FPS = 30;
export const CLIP_HQ_MAX_WIDTH = 2560;
export const CLIP_HQ_MAX_HEIGHT = 1600;
export const CLIP_HQ_BITS_PER_PIXEL_FRAME = 0.04;
export const CLIP_HQ_MIN_BPS = 2_000_000;
export const CLIP_HQ_MAX_BPS = 10_000_000;
export const CLIP_HQ_TIMESLICE_MS = 1_000;
/** No data from a capture this long: it is stuck, start it again. */
export const CLIP_HQ_STALL_MS = 15_000;
export const CLIP_HQ_START_TIMEOUT_MS = 15_000;
export const CLIP_HQ_STOP_TIMEOUT_MS = 5_000;
export const CLIP_HQ_RETRY_MS = Object.freeze([2_000, 5_000, 10_000, 30_000, 60_000]);
/** "Save the last 5 min". */
export const CLIP_LAST_N_SEC = 5 * 60;
/** Where each tab was, kept in memory so "save the last 5 min" knows the past. */
export const CLIP_TAB_HISTORY_SEC = 30 * 60;
/** A manifest line per minute while a clip is open, so a restart can say how long Nova was down. */
export const CLIP_BEAT_MS = 60_000;
export const CLIP_WATCH_MS = 1_000;
export const CLIP_REPORT_MS = 10_000;
/** The view lists at most this many clips, newest first. */
export const CLIP_VIEW_MAX = 200;
/** Exports: at most this wide and tall, even on both sides (H.264). */
export const CLIP_OUT_MAX_WIDTH = 1920;
export const CLIP_OUT_MAX_HEIGHT = 1200;
export const CLIP_OUT_BITS_PER_PIXEL_FRAME = 0.07;
export const CLIP_OUT_MIN_BPS = 1_500_000;
export const CLIP_OUT_MAX_BPS = 12_000_000;
/** An export frame rate when the clip is all cut (the screen recording's own). */
export const CLIP_OUT_CUT_FPS = 15;
export const CLIP_PREVIEW_MAX_WIDTH = 1280;
export const CLIP_DIR_ENV = 'NOVA_CLIPS_DIR';
export const CLIP_DATA_DRIVE = 'F:\\';
export const CLIP_DATA_DIR = 'F:\\Nova\\clips';
export const CLIP_FALLBACK_SUBDIR = 'clips';
export const CLIP_MANIFEST = 'clips.jsonl';
export const CLIP_HQ_SUBDIR = 'hq';
export const CLIP_PICTURES = Object.freeze(['trader_tab', 'panels', 'window', 'monitor']);
/** Panels the page reports inside a Trader tab (their data-testid, frontend/src/clips/clipTabReport.ts). */
export const CLIP_PANELS = Object.freeze(['charts', 'level2', 'tape', 'quote', 'plan', 'ticket', 'orders']);
/** The first supported wins (MediaRecorder.isTypeSupported in the capture page). */
export const CLIP_HQ_MIMES = Object.freeze([
  'video/x-matroska;codecs=avc1',
  'video/webm;codecs=h264',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
]);

const ET = 'America/New_York';
const etFormat = new Intl.DateTimeFormat('en-US', {
  timeZone: ET,
  hourCycle: 'h23',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

/** `{date: 'YYYY-MM-DD', time: 'HHMMSS'}` on the Eastern clock. */
export function etParts(ms) {
  const p = Object.fromEntries(etFormat.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour}${p.minute}${p.second}` };
}

/** Every Eastern date from `startMs` to `endMs`, in order (a clip over midnight reads two days of recordings). */
export function etDates(startMs, endMs) {
  const out = [];
  for (let t = startMs; t <= endMs + 1; t += 6 * 3_600_000) {
    const { date } = etParts(t);
    if (out[out.length - 1] !== date) out.push(date);
  }
  const last = etParts(endMs).date;
  if (out[out.length - 1] !== last) out.push(last);
  return out;
}

export const SYMBOL_RE = /^[A-Z][A-Z0-9./-]{0,11}$/;
export const cleanSymbol = (s) => {
  const up = String(s ?? '').trim().toUpperCase();
  return SYMBOL_RE.test(up) ? up : null;
};
const fileSafe = (symbol) => symbol.replace(/[./]/g, '-');

/**
 * Where clips go: `NOVA_CLIPS_DIR`, else `F:\Nova\clips` while F: is mounted,
 * else the app's own folder, and the view says so.
 */
export function resolveClipDir({ env = {}, dataDriveMounted, userData, join }) {
  const fromEnv = String(env[CLIP_DIR_ENV] ?? '').trim();
  if (fromEnv) return { dir: fromEnv, source: 'env', note: null };
  if (dataDriveMounted) return { dir: CLIP_DATA_DIR, source: 'data_drive', note: null };
  return {
    dir: join(userData, CLIP_FALLBACK_SUBDIR),
    source: 'fallback',
    note: `${CLIP_DATA_DRIVE.slice(0, 2)} is not mounted, so clips go to the system drive`,
  };
}

/** `<date>/<SYMBOL>-<HHMMSS>.mp4`, the Eastern date and time the clip starts. */
export function exportRelPath(startMs, symbol, attempt = 1) {
  const { date, time } = etParts(startMs);
  return { date, name: `${fileSafe(symbol)}-${time}${attempt > 1 ? `-${attempt}` : ''}.mp4` };
}

/** `hq/<date>/<HHMMSS>-<SYMBOL>-hq.<ext>`: one file per high-quality capture. */
export function hqRelPath(startMs, symbol, mime, attempt = 1) {
  const { date, time } = etParts(startMs);
  const ext = /h264|avc1/i.test(String(mime)) ? 'mkv' : 'webm';
  return { date, name: `${time}-${fileSafe(symbol)}-hq${attempt > 1 ? `-${attempt}` : ''}.${ext}` };
}

const even = (n) => Math.max(2, Math.floor(n / 2) * 2);

/** The capture size and bitrate for a window of `width` x `height` physical pixels. */
export function hqPlan(width, height, fps = CLIP_HQ_FPS) {
  const w = Math.max(2, width || 1920);
  const h = Math.max(2, height || 1080);
  const scale = Math.min(1, CLIP_HQ_MAX_WIDTH / w, CLIP_HQ_MAX_HEIGHT / h);
  const cw = even(w * scale);
  const ch = even(h * scale);
  const bps = Math.min(CLIP_HQ_MAX_BPS, Math.max(CLIP_HQ_MIN_BPS, Math.round(cw * ch * fps * CLIP_HQ_BITS_PER_PIXEL_FRAME)));
  return { maxWidth: cw, maxHeight: ch, fps, bps };
}

export function outputBitrate(width, height, fps) {
  const bps = Math.round(width * height * fps * CLIP_OUT_BITS_PER_PIXEL_FRAME);
  return Math.min(CLIP_OUT_MAX_BPS, Math.max(CLIP_OUT_MIN_BPS, bps));
}

/** An export's size for a picture `w` x `h` DIP: the tab as it is, capped, even on both sides. */
export function outputSize(w, h) {
  const scale = Math.min(1, CLIP_OUT_MAX_WIDTH / Math.max(1, w), CLIP_OUT_MAX_HEIGHT / Math.max(1, h));
  return { width: even(w * scale), height: even(h * scale) };
}

export function retryDelayMs(failures) {
  const i = Math.min(Math.max(0, failures - 1), CLIP_HQ_RETRY_MS.length - 1);
  return CLIP_HQ_RETRY_MS[i];
}

const finite = (v) => typeof v === 'number' && Number.isFinite(v);
/** A rectangle `{x, y, w, h}` with finite numbers and a positive size, else null. */
export function readRect(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const x = raw.x;
  const y = raw.y;
  const w = raw.w ?? raw.width;
  const h = raw.h ?? raw.height;
  if (![x, y, w, h].every(finite) || w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}

/** The union of rectangles, or null when there are none. */
export function unionRect(rects) {
  const list = (rects || []).filter(Boolean);
  if (!list.length) return null;
  const x0 = Math.min(...list.map((r) => r.x));
  const y0 = Math.min(...list.map((r) => r.y));
  const x1 = Math.max(...list.map((r) => r.x + r.w));
  const y1 = Math.max(...list.map((r) => r.y + r.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

/** CSS pixels on the page to DIP inside the window's content area. */
export function cssToDip(rect, geometry) {
  const k = geometry.content.width / Math.max(1, geometry.inner.w);
  return { x: rect.x * k, y: rect.y * k, w: rect.w * k, h: rect.h * k };
}

/** Clamp a pixel rectangle into a `fw` x `fh` frame; whole pixels; null when nothing is left. */
export function clampRect(r, fw, fh) {
  const x0 = Math.max(0, Math.floor(r.x));
  const y0 = Math.max(0, Math.floor(r.y));
  const x1 = Math.min(fw, Math.ceil(r.x + r.w));
  const y1 = Math.min(fh, Math.ceil(r.y + r.h));
  return x1 - x0 >= 2 && y1 - y0 >= 2 ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
}

/**
 * A rectangle in DIP inside the window's content area, in pixels of a screen
 * segment that recorded `display` (its DIP bounds) at `width` x `height`.
 */
export function dipToScreenFrame(dip, geometry, display, width, height) {
  const b = display.bounds;
  const sx = width / b.width;
  const sy = height / b.height;
  const X = geometry.content.x + dip.x;
  const Y = geometry.content.y + dip.y;
  return clampRect({ x: (X - b.x) * sx, y: (Y - b.y) * sy, w: dip.w * sx, h: dip.h * sy }, width, height);
}

/** The picture a clip shows at one geometry, in DIP inside the content area (null: nothing to show). */
export function pictureDip(geometry, picture, panels = []) {
  if (!geometry) return null;
  if (picture === 'window') return { x: 0, y: 0, w: geometry.content.width, h: geometry.content.height };
  if (picture === 'panels') {
    const rects = panels.map((id) => readRect(geometry.panels?.[id])).filter(Boolean);
    const u = unionRect(rects);
    return u ? cssToDip(u, geometry) : null;
  }
  const pane = readRect(geometry.pane);
  return pane ? cssToDip(pane, geometry) : null;
}

/** The display a geometry's picture sits on: the one holding its centre, else the first that overlaps. */
export function displayFor(geometry, displays) {
  const pic = pictureDip(geometry, 'trader_tab') ?? { x: 0, y: 0, w: geometry.content.width, h: geometry.content.height };
  const cx = geometry.content.x + pic.x + pic.w / 2;
  const cy = geometry.content.y + pic.y + pic.h / 2;
  const inside = (d) => cx >= d.bounds.x && cx < d.bounds.x + d.bounds.width && cy >= d.bounds.y && cy < d.bounds.y + d.bounds.height;
  return (displays || []).find(inside) ?? null;
}
