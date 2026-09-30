/**
 * Share clips (ADR 039): what an export reads, pure. A clip's stretch is cut
 * into slices wherever something changes -- its geometry, whether the tab
 * showed, a high-quality file, a screen segment, a restart -- and each slice
 * takes its picture from the high-quality capture when one ran in the tab's
 * window, else from the screen segment of the tab's monitor (the fallback that
 * leaves no hole). Stretches with no picture, and hidden ones the operator
 * cuts, are left out and counted. The same slices draw the export dialog's
 * tracks (`clipTimeline`).
 */
import {
  CLIP_HQ_FPS,
  CLIP_OUT_CUT_FPS,
  cssToDip,
  dipToScreenFrame,
  outputBitrate,
  outputSize,
  pictureDip,
  readRect,
} from './clipPlan.mjs';
import { UNKNOWN_STATE, geometryAt, hqSpans, restartGaps, visibilitySpans } from './clipManifest.mjs';

/** Screen segments' ends, sorted; `{file, startedTs, endedTs, display: {id, index, bounds}, width, height}`. */
const covering = (list, t) => list.find((s) => s.startedTs <= t && t < s.endedTs) ?? null;
const inAny = (spans, t) => spans.some((s) => s.start <= t && t < s.end);

function screenSegmentFor(segments, geometry, dip, t) {
  const cx = geometry.content.x + dip.x + dip.w / 2;
  const cy = geometry.content.y + dip.y + dip.h / 2;
  return segments.find((s) => {
    const b = s.display?.bounds;
    return b && s.startedTs <= t && t < s.endedTs && cx >= b.x && cx < b.x + b.width && cy >= b.y && cy < b.y + b.height;
  }) ?? null;
}

/** Every change point inside `[from, to)`, sorted, with both ends. */
function boundaries(clip, segments, hq, from, to) {
  const pts = new Set([from, to]);
  const add = (t) => {
    if (typeof t === 'number' && t > from && t < to) pts.add(t);
  };
  for (const m of clip.marks) add(m.ts);
  add(clip.endedTs);
  for (const s of segments) { add(s.startedTs); add(s.endedTs); }
  for (const s of hq) { add(s.start); add(s.end); }
  for (const g of restartGaps(clip)) { add(g.start); add(g.end); }
  return [...pts].sort((a, b) => a - b);
}

/**
 * The slices of `[from, to)`: `{start, end, gap, shown, showing, reason,
 * geometry, hq, screen}` -- `hq` / `screen` the source that covers the slice
 * (null when none does).
 */
export function sliceClip({ clip, screenSegments, from, to, now }) {
  const hq = hqSpans(clip, now);
  const gaps = restartGaps(clip);
  const vis = visibilitySpans(clip, from, to);
  const pts = boundaries(clip, screenSegments, hq, from, to);
  const out = [];
  for (let i = 0; i + 1 < pts.length; i += 1) {
    const start = pts[i];
    const end = pts[i + 1];
    if (end - start < 0.001) continue;
    const mid = (start + end) / 2;
    const v = vis.find((s) => s.start <= mid && mid < s.end) ?? UNKNOWN_STATE;
    const geometry = geometryAt(clip, mid);
    const dip = geometry ? pictureDip(geometry, 'trader_tab') : null;
    const h = geometry ? hq.find((s) => s.start <= mid && mid < s.end && s.windowId === geometry.window_id) ?? null : null;
    const screen = geometry && dip ? screenSegmentFor(screenSegments, geometry, dip, mid) : covering(screenSegments, mid);
    out.push({ start, end, gap: inAny(gaps, mid), shown: v.shown, showing: v.showing, reason: v.reason, geometry, hq: h, screen });
  }
  return out;
}

function sourceFor(slice, picture) {
  if (slice.gap || !slice.geometry) return null;
  if (slice.hq && picture !== 'monitor') return { kind: 'hq', seg: slice.hq };
  if (slice.screen) return { kind: 'screen', seg: slice.screen };
  return null;
}

function cropFor(seg, geometry, dip, picture) {
  if (picture === 'monitor') return { x: 0, y: 0, w: seg.width, h: seg.height };
  return dipToScreenFrame(dip, geometry, seg.display, seg.width, seg.height);
}

/**
 * Blur boxes in the crop's own source pixels (relative to its corner): each
 * panel mapped like the crop and cut to it. The export page fits the crop into
 * the output and the boxes with it, so a letterboxed piece blurs the right place.
 */
function blurFor(seg, geometry, crop, blur) {
  const boxes = [];
  for (const id of blur || []) {
    const css = readRect(geometry.panels?.[id]);
    if (!css) continue;
    const px = dipToScreenFrame(cssToDip(css, geometry), geometry, seg.display, seg.width, seg.height);
    if (!px) continue;
    const x0 = Math.max(0, px.x - crop.x);
    const y0 = Math.max(0, px.y - crop.y);
    const x1 = Math.min(crop.w, px.x + px.w - crop.x);
    const y1 = Math.min(crop.h, px.y + px.h - crop.y);
    if (x1 - x0 >= 2 && y1 - y0 >= 2) boxes.push({ x: Math.round(x0), y: Math.round(y0), w: Math.round(x1 - x0), h: Math.round(y1 - y0) });
  }
  return boxes;
}

/**
 * A high-quality piece's picture, left to the export page: a window capture's
 * frame size is only known per decoded frame (it is the window's visible
 * rectangle, and follows a resize), so the piece carries the picture and the
 * blur panels in DIP inside the page, with the page's size.
 */
function windowSpec(geometry, dip, picture, blur) {
  const panels = (blur || []).map((id) => readRect(geometry.panels?.[id])).filter(Boolean).map((css) => cssToDip(css, geometry));
  return {
    dip: picture === 'window' ? null : dip,
    content: { width: geometry.content.width, height: geometry.content.height },
    blur: panels,
  };
}

const round3 = (v) => Math.round(v * 1000) / 1000;

/** Why a stretch has nothing to export, from what was left out. */
function nothingError(counts) {
  const other = counts.hidden_sec + counts.gap_sec + counts.no_picture_sec;
  if (counts.unknown_sec > 0 && other === 0) return 'Nova was not following the tab then (it follows a tab while a clip records, and keeps 30 min of where each tab was)';
  if (counts.hidden_sec > 0 && counts.no_picture_sec === 0 && counts.gap_sec === 0) return 'the tab showed something else for all of it';
  if (counts.gap_sec > 0 && counts.no_picture_sec === 0) return 'Nova was down for all of it';
  return 'nothing in this stretch has a picture';
}

/**
 * The export: `{out: {width, height, fps, bitrate}, pieces: [{kind, file,
 * t0, t1, out0, crop, blur}], duration, counts: {hq_sec, screen_sec,
 * hidden_sec, gap_sec, unknown_sec, no_picture_sec}}`, or `{error}` when
 * nothing can be shown. `t0` / `t1` are seconds into the source file, `out0`
 * into the export. A stretch Nova did not follow the tab (`unknown_sec`) is
 * always left out: nothing says where the tab was.
 */
export function buildExportPlan({ clip, settings, screenSegments, now }) {
  const picture = settings.picture ?? 'trader_tab';
  const panels = Array.isArray(settings.panels) ? settings.panels : [];
  const from = settings.start_ts;
  const to = Math.min(settings.end_ts, now);
  if (!(typeof from === 'number' && typeof to === 'number' && to > from)) return { error: 'the stretch to export is empty' };
  const slices = sliceClip({ clip, screenSegments, from, to, now });
  const counts = { hq_sec: 0, screen_sec: 0, hidden_sec: 0, gap_sec: 0, unknown_sec: 0, no_picture_sec: 0 };
  const kept = [];
  for (const s of slices) {
    const len = s.end - s.start;
    if (s.gap) { counts.gap_sec += len; continue; }
    // Nova was not following the tab (before the clip's first mark, after its stop): where it was is not known.
    if (s.reason === 'unknown') { counts.unknown_sec += len; continue; }
    if (!s.shown && settings.cut_hidden) { counts.hidden_sec += len; continue; }
    const src = sourceFor(s, picture);
    const dip = s.geometry && pictureDip(s.geometry, picture === 'monitor' ? 'trader_tab' : picture, panels);
    if (!src || (!dip && picture !== 'monitor')) { counts.no_picture_sec += len; continue; }
    kept.push({ ...s, src, dip });
  }
  if (!kept.length) return { error: nothingError(counts), counts };
  const first = kept[0];
  const size = picture === 'monitor'
    ? outputSize(first.src.kind === 'screen' ? first.src.seg.display.bounds.width : first.dip.w, first.src.kind === 'screen' ? first.src.seg.display.bounds.height : first.dip.h)
    : outputSize(first.dip.w, first.dip.h);
  const fps = kept.some((s) => s.src.kind === 'hq') ? CLIP_HQ_FPS : CLIP_OUT_CUT_FPS;
  const out = { ...size, fps, bitrate: outputBitrate(size.width, size.height, fps) };
  const pieces = [];
  let cursor = 0;
  for (const s of kept) {
    const seg = s.src.seg;
    const len = s.end - s.start;
    const hqPiece = s.src.kind === 'hq';
    const crop = hqPiece ? null : cropFor(seg, s.geometry, s.dip, picture);
    if (!hqPiece && !crop) { counts.no_picture_sec += len; continue; }
    const base = hqPiece ? seg.start : seg.startedTs;
    const piece = {
      kind: s.src.kind,
      file: seg.file,
      t0: round3(s.start - base),
      t1: round3(s.end - base),
      out0: round3(cursor),
      crop,
      blur: hqPiece ? [] : blurFor(seg, s.geometry, crop, settings.blur),
      window: hqPiece ? windowSpec(s.geometry, s.dip, picture, settings.blur) : null,
    };
    const prev = pieces[pieces.length - 1];
    const same = prev && prev.kind === piece.kind && prev.file === piece.file
      && Math.abs(prev.t1 - piece.t0) < 0.002 && JSON.stringify([prev.crop, prev.blur, prev.window]) === JSON.stringify([piece.crop, piece.blur, piece.window]);
    if (same) prev.t1 = piece.t1;
    else pieces.push(piece);
    counts[s.src.kind === 'hq' ? 'hq_sec' : 'screen_sec'] += len;
    cursor += len;
  }
  if (!pieces.length) return { error: nothingError(counts), counts };
  for (const k of Object.keys(counts)) counts[k] = Math.round(counts[k] * 10) / 10;
  return { out, pieces, duration: round3(cursor), counts, picture };
}

/**
 * The export dialog's tracks over `[from, to)`: `{screen, hq, shown, hidden,
 * unknown, gaps}`, each a list of `[start, end]` (hidden: `{start, end,
 * showing, reason}`); `unknown` is where Nova was not following the tab.
 */
export function clipTimeline({ clip, screenSegments, from, to, now }) {
  const slices = sliceClip({ clip, screenSegments, from, to, now });
  const merge = (pick) => slices.filter(pick).reduce((acc, s) => {
    const last = acc[acc.length - 1];
    if (last && Math.abs(last[1] - s.start) < 0.002) last[1] = s.end;
    else acc.push([s.start, s.end]);
    return acc;
  }, []);
  const hidden = [];
  for (const s of slices) {
    if (s.shown || s.gap || s.reason === 'unknown') continue;
    const last = hidden[hidden.length - 1];
    if (last && last.showing === s.showing && last.reason === s.reason && Math.abs(last.end - s.start) < 0.002) last.end = s.end;
    else hidden.push({ start: s.start, end: s.end, showing: s.showing ?? null, reason: s.reason ?? null });
  }
  return {
    screen: merge((s) => Boolean(s.screen) && !s.gap),
    hq: merge((s) => Boolean(s.hq) && !s.gap),
    shown: merge((s) => s.shown && !s.gap),
    hidden,
    unknown: merge((s) => s.reason === 'unknown' && !s.gap),
    gaps: merge((s) => s.gap),
  };
}
