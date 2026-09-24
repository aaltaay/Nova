/**
 * The trading screen recording (ADR 035), the pure half: what to record for
 * each monitor, where the files go, and what they are called. No electron or
 * node imports, so it is testable as is and the recorder page can share the
 * constants it needs through the start command.
 *
 * Every monitor is captured at its Windows layout size (a 4K monitor at 150%
 * records at 2560x1440): text stays as legible as on a 100% monitor, at a
 * quarter of the pixels a native 4K capture would encode. H.264 in Matroska
 * when Chromium can encode it -- sharper text than VP9 at under half the size
 * on this desk (probe, 2026-09-24), and a Matroska file cut short by a crash
 * still plays up to its last cluster.
 */

export const SCREEN_RECORD_SCHEMA_VERSION = 1;
export const SCREEN_RECORD_FPS = 15;
/** MediaRecorder hands over data every timeslice; a crash loses at most this much. */
export const SCREEN_RECORD_TIMESLICE_MS = 1_000;
/** A new file per monitor every quarter hour, on the quarter hour (ET quarters are UTC quarters). */
export const SCREEN_RECORD_SEGMENT_MS = 15 * 60_000;
/** Bitrate = pixels x fps x this: 2560x1440 at 15 fps is about 2.5 Mbps (a cap; still screens use far less). */
export const SCREEN_RECORD_BITS_PER_PIXEL_FRAME = 0.045;
export const SCREEN_RECORD_MIN_BPS = 1_000_000;
export const SCREEN_RECORD_MAX_BPS = 8_000_000;
export const SCREEN_RECORD_MAX_WIDTH = 3840;
export const SCREEN_RECORD_MAX_HEIGHT = 2160;
/** First supported wins (MediaRecorder.isTypeSupported in the recorder page). */
export const SCREEN_RECORD_MIMES = Object.freeze([
  'video/x-matroska;codecs=avc1',
  'video/webm;codecs=h264',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
]);
export const SCREEN_RECORD_DIR_ENV = 'NOVA_SCREEN_RECORD_DIR';
export const SCREEN_RECORD_DATA_DRIVE = 'F:\\';
export const SCREEN_RECORD_DATA_DIR = 'F:\\Nova\\screen';
export const SCREEN_RECORD_FALLBACK_SUBDIR = 'screen';
export const SCREEN_RECORD_MANIFEST = 'segments.jsonl';
/** No data from a recorder this long: it is stuck, start that monitor again. */
export const SCREEN_RECORD_STALL_MS = 12_000;
/** A start that has not begun recording by now failed. */
export const SCREEN_RECORD_START_TIMEOUT_MS = 15_000;
/** A stop whose last data never arrives is closed anyway after this. */
export const SCREEN_RECORD_STOP_TIMEOUT_MS = 5_000;
/** Waits before starting a failed monitor again; the last one repeats forever -- it never gives up. */
export const SCREEN_RECORD_RETRY_MS = Object.freeze([2_000, 5_000, 10_000, 30_000, 60_000]);
export const SCREEN_RECORD_WATCH_MS = 3_000;
export const SCREEN_RECORD_DISPLAY_SETTLE_MS = 2_000;
export const SCREEN_RECORD_DISK_CHECK_MS = 60_000;
/** Mirrors backend constants_screen_record.py (and the leaderboard's drive guard, #485). */
export const SCREEN_RECORD_FREE_WARN_BYTES = 50 * 1024 ** 3;
export const SCREEN_RECORD_FREE_FAIL_BYTES = 10 * 1024 ** 3;
export const SCREEN_RECORD_PROBLEMS_KEEP = 10;
export const SCREEN_RECORD_REPORT_MS = 10_000;

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

/** The next quarter-hour boundary strictly after `now` (epoch ms). */
export function nextBoundaryMs(now, segmentMs = SCREEN_RECORD_SEGMENT_MS) {
  return (Math.floor(now / segmentMs) + 1) * segmentMs;
}

const even = (n) => Math.max(2, Math.floor(n / 2) * 2);

/** The capture size for a display: its Windows layout size, capped, even (H.264 needs even sides). */
export function captureSize(display) {
  const w = display?.size?.width ?? display?.bounds?.width ?? 1920;
  const h = display?.size?.height ?? display?.bounds?.height ?? 1080;
  const scale = Math.min(1, SCREEN_RECORD_MAX_WIDTH / w, SCREEN_RECORD_MAX_HEIGHT / h);
  return { width: even(w * scale), height: even(h * scale) };
}

export function bitrateFor(width, height, fps = SCREEN_RECORD_FPS) {
  const bps = Math.round(width * height * fps * SCREEN_RECORD_BITS_PER_PIXEL_FRAME);
  return Math.min(SCREEN_RECORD_MAX_BPS, Math.max(SCREEN_RECORD_MIN_BPS, bps));
}

/** `.mkv` for H.264 (Matroska; Windows plays it), `.webm` for VP8 / VP9. */
export function extensionFor(mime) {
  return /h264|avc1/i.test(String(mime)) ? 'mkv' : 'webm';
}

/** Monitors left to right, then top to bottom: the leftmost is monitor 1 (focusSensor.mjs's order). */
export function orderDisplays(displays) {
  return [...(displays || [])].sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
}

/**
 * One capture plan per monitor that has a screen source. `sources` are
 * desktopCapturer screen sources ({id, display_id}); a monitor with no source
 * is left out and named in `unmatched`, never guessed.
 */
export function planDisplays({ displays, sources, primaryId, fps = SCREEN_RECORD_FPS }) {
  const ordered = orderDisplays(displays);
  const bySource = new Map((sources || []).map((s) => [String(s.display_id ?? ''), s]));
  const plans = [];
  const unmatched = [];
  ordered.forEach((d, i) => {
    const source = bySource.get(String(d.id));
    const display = {
      id: String(d.id),
      index: i + 1,
      count: ordered.length,
      label: d.label ? String(d.label).slice(0, 120) : null,
      primary: d.id === primaryId,
      scale_factor: typeof d.scaleFactor === 'number' && d.scaleFactor > 0 ? d.scaleFactor : null,
      bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
    };
    if (!source) {
      unmatched.push(display);
      return;
    }
    const { width, height } = captureSize(d);
    plans.push({ key: display.id, sourceId: String(source.id), display, width, height, fps, bps: bitrateFor(width, height, fps) });
  });
  // One screen source Windows could not tie to a display id (seen with some drivers): record it anyway.
  if (!plans.length && (sources || []).length === 1 && ordered.length === 1) {
    const d = ordered[0];
    const { width, height } = captureSize(d);
    const display = unmatched.shift();
    plans.push({ key: display.id, sourceId: String(sources[0].id), display, width, height, fps, bps: bitrateFor(width, height, fps) });
  }
  return { plans, unmatched };
}

/**
 * Two plans record the same picture (same source, size, rate): a display event
 * that changed nothing -- or only renumbered the monitors -- restarts nothing.
 */
export function samePlan(a, b) {
  return Boolean(a && b) && a.sourceId === b.sourceId && a.width === b.width && a.height === b.height && a.fps === b.fps;
}

/**
 * Where the files go: `NOVA_SCREEN_RECORD_DIR`, else `F:\Nova\screen` while F:
 * is mounted, else the app's own folder -- recording on C: beats not
 * recording, and the view says so (`dir_source: "fallback"`).
 */
export function resolveRecordDir({ env = {}, dataDriveMounted, userData, join }) {
  const fromEnv = String(env[SCREEN_RECORD_DIR_ENV] ?? '').trim();
  if (fromEnv) return { dir: fromEnv, source: 'env', note: null };
  if (dataDriveMounted) return { dir: SCREEN_RECORD_DATA_DIR, source: 'data_drive', note: null };
  return {
    dir: join(userData, SCREEN_RECORD_FALLBACK_SUBDIR),
    source: 'fallback',
    note: `${SCREEN_RECORD_DATA_DRIVE.slice(0, 2)} is not mounted, so the screen records to the system drive`,
  };
}

/** `<date>/<HHMMSS>-screen<N>.<ext>`, the date and time the segment started on the Eastern clock. */
export function segmentRelPath(startMs, displayIndex, mime, attempt = 1) {
  const { date, time } = etParts(startMs);
  const dup = attempt > 1 ? `-${attempt}` : '';
  return { date, name: `${time}-screen${displayIndex}${dup}.${extensionFor(mime)}` };
}

export function diskState(freeBytes) {
  if (typeof freeBytes !== 'number' || !Number.isFinite(freeBytes)) return 'unknown';
  if (freeBytes < SCREEN_RECORD_FREE_FAIL_BYTES) return 'fail';
  if (freeBytes < SCREEN_RECORD_FREE_WARN_BYTES) return 'warn';
  return 'ok';
}

export function retryDelayMs(failures) {
  const i = Math.min(Math.max(0, failures - 1), SCREEN_RECORD_RETRY_MS.length - 1);
  return SCREEN_RECORD_RETRY_MS[i];
}
