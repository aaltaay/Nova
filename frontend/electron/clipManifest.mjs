/**
 * Share clips (ADR 039): the clip manifest, folded. `<clips dir>/clips.jsonl`
 * holds one JSON object per line with `schema_version: 1` and `event` (the
 * shapes are in AGENTS.md §3, "Share clips"); this module turns those rows
 * into each clip's state and the spans the export and the chips need. Pure:
 * no fs, no electron.
 *
 * A clip is marks on the screen recording: `open` (and a `close` once the
 * operator stops it -- a quit never closes one, a restart only marks the gap),
 * `mark` rows saying where its Trader tab was and whether it showed, `hq`
 * rows for each high-quality capture file, `set` when High quality is turned
 * on or off, `export` rows for each export's progress, and `delete`.
 */
import { CLIP_SCHEMA_VERSION } from './clipPlan.mjs';

export const CLIP_EVENTS = Object.freeze(['open', 'set', 'mark', 'hq', 'close', 'beat', 'export', 'delete']);
export const CLIP_MARK_KINDS = Object.freeze(['shown', 'hidden', 'geometry', 'restart']);
export const CLIP_EXPORT_STATES = Object.freeze(['queued', 'running', 'done', 'failed', 'cancelled']);

const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v) => (typeof v === 'string' && v.length ? v : null);

function newClip(row) {
  return {
    id: row.clip_id,
    symbol: String(row.symbol || ''),
    origin: str(row.origin) ?? 'button',
    picture: str(row.picture) ?? 'trader_tab',
    openedTs: num(row.ts),
    startedTs: num(row.started_ts) ?? num(row.ts),
    endedTs: null,
    closeReason: null,
    hqWanted: row.hq === true,
    hqSince: row.hq === true ? num(row.ts) : null,
    marks: [],
    hq: [],
    exports: new Map(),
    deleted: false,
    lastBeatTs: num(row.ts),
  };
}

/** Apply one manifest row to `clips` (a Map); returns false for a row it cannot read. */
export function applyRow(clips, row) {
  if (!row || typeof row !== 'object' || row.schema_version !== CLIP_SCHEMA_VERSION) return false;
  if (!CLIP_EVENTS.includes(row.event)) return false;
  const ts = num(row.ts);
  if (ts === null) return false;
  if (row.event === 'beat') {
    for (const id of Array.isArray(row.clip_ids) ? row.clip_ids : []) {
      const c = clips.get(id);
      if (c) c.lastBeatTs = ts;
    }
    return true;
  }
  const id = str(row.clip_id);
  if (!id) return false;
  if (row.event === 'open') {
    if (!clips.has(id)) clips.set(id, newClip(row));
    return true;
  }
  const clip = clips.get(id);
  if (!clip) return false;
  clip.lastBeatTs = Math.max(clip.lastBeatTs ?? ts, ts);
  switch (row.event) {
    case 'set':
      clip.hqWanted = row.hq === true;
      clip.hqSince = clip.hqWanted ? ts : null;
      return true;
    case 'mark':
      if (!CLIP_MARK_KINDS.includes(row.kind)) return false;
      clip.marks.push({ ts, kind: row.kind, detail: row.detail && typeof row.detail === 'object' ? row.detail : {} });
      clip.marks.sort((a, b) => a.ts - b.ts);
      return true;
    case 'hq':
      if (row.state === 'start' && str(row.file)) {
        clip.hq.push({
          start: ts,
          end: null,
          file: row.file,
          windowId: str(row.window_id),
          reason: null,
        });
      } else if (row.state === 'end') {
        const open = [...clip.hq].reverse().find((s) => s.end === null && (!row.file || s.file === row.file));
        if (open) {
          open.end = ts;
          open.reason = str(row.reason);
          open.error = str(row.error);
        }
      } else {
        return false;
      }
      return true;
    case 'close':
      clip.endedTs = num(row.ended_ts) ?? ts;
      clip.closeReason = str(row.reason) ?? 'operator';
      return true;
    case 'export': {
      const exportId = str(row.export_id);
      if (!exportId || !CLIP_EXPORT_STATES.includes(row.state)) return false;
      const prev = clip.exports.get(exportId) ?? { exportId, queuedTs: ts };
      clip.exports.set(exportId, {
        ...prev,
        ts,
        state: row.state,
        file: str(row.file) ?? prev.file ?? null,
        bytes: num(row.bytes) ?? prev.bytes ?? null,
        error: str(row.error),
        note: str(row.note) ?? prev.note ?? null,
        settings: row.settings && typeof row.settings === 'object' ? row.settings : prev.settings ?? null,
      });
      return true;
    }
    case 'delete':
      clip.deleted = true;
      return true;
    default:
      return false;
  }
}

/** Every row folded, in order: `{clips, skipped}` -- a line it cannot read is counted, never guessed. */
export function foldRows(rows) {
  const clips = new Map();
  let skipped = 0;
  for (const row of rows) if (!applyRow(clips, row)) skipped += 1;
  return { clips, skipped };
}

/** Parse `clips.jsonl` text into rows; a line that is not JSON is counted in `bad`. */
export function parseManifest(text) {
  const rows = [];
  let bad = 0;
  for (const line of String(text || '').split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      rows.push(JSON.parse(line));
    } catch {
      bad += 1;
    }
  }
  return { rows, bad };
}

export const isOpen = (clip) => clip.endedTs === null && !clip.deleted;

/** The last geometry at or before `ts`, else the first one after it; null when the clip has none. */
export function geometryAt(clip, ts) {
  let before = null;
  let after = null;
  for (const m of clip.marks) {
    if (m.kind !== 'geometry') continue;
    if (m.ts <= ts) before = m;
    else if (!after) after = m;
  }
  return (before ?? after)?.detail ?? null;
}

/** The times the clip's geometry changes inside `[start, end)`. */
export function geometryTimes(clip, start, end) {
  return clip.marks.filter((m) => m.kind === 'geometry' && m.ts > start && m.ts < end).map((m) => m.ts);
}

/** Nova was not following the tab: before a clip's first mark, and after it stopped. */
export const UNKNOWN_STATE = Object.freeze({ shown: false, reason: 'unknown', showing: null });

/**
 * When the tab showed the clip's symbol, `[{start, end, shown, reason, showing}]`
 * covering `[from, to)`. Nova knows only what it marked: before the first shown
 * / hidden mark, and after a stopped clip's end, the state is not known
 * (`reason: "unknown"`), never taken to be shown.
 */
export function visibilitySpans(clip, from, to) {
  const known = clip.marks
    .filter((m) => m.kind === 'shown' || m.kind === 'hidden')
    .map((m) => ({
      ts: m.ts,
      state: m.kind === 'shown'
        ? { shown: true, reason: null, showing: null }
        : { shown: false, reason: str(m.detail.reason) ?? 'hidden', showing: str(m.detail.showing) },
    }));
  const changes = clip.endedTs === null
    ? known
    : [...known.filter((c) => c.ts < clip.endedTs), { ts: clip.endedTs, state: UNKNOWN_STATE }];
  let state = UNKNOWN_STATE;
  const out = [];
  let cursor = from;
  for (const c of changes) {
    if (c.ts <= from) {
      state = c.state;
      continue;
    }
    if (c.ts >= to) break;
    if (c.ts > cursor) out.push({ start: cursor, end: c.ts, ...state });
    cursor = c.ts;
    state = c.state;
  }
  if (to > cursor) out.push({ start: cursor, end: to, ...state });
  // Neighbours in the same state are one stretch.
  return out.reduce((acc, s) => {
    const last = acc[acc.length - 1];
    if (last && last.shown === s.shown && last.reason === s.reason && last.showing === s.showing && last.end === s.start) last.end = s.end;
    else acc.push({ ...s });
    return acc;
  }, []);
}

/** The stretches Nova was down while the clip was open: `[{start, end}]` from each restart mark. */
export function restartGaps(clip) {
  return clip.marks
    .filter((m) => m.kind === 'restart' && num(m.detail.down_since) !== null && m.detail.down_since < m.ts)
    .map((m) => ({ start: m.detail.down_since, end: m.ts }));
}

/** High-quality capture files, `[{start, end, file, frame, windowId, reason}]`; an open one ends at `now`. */
export function hqSpans(clip, now) {
  return clip.hq.map((s) => ({ ...s, end: s.end ?? now }));
}

export function latestExport(clip) {
  let last = null;
  for (const e of clip.exports.values()) if (!last || e.queuedTs >= last.queuedTs) last = e;
  return last;
}

/** A clip's place in its life: recording, not exported, queued, exporting, ready, failed or cancelled. */
export function clipStatus(clip) {
  if (isOpen(clip)) return 'recording';
  const e = latestExport(clip);
  if (!e) return 'not_exported';
  if (e.state === 'done') return 'ready';
  if (e.state === 'running') return 'exporting';
  return e.state;
}

const sum = (spans) => spans.reduce((t, s) => t + Math.max(0, s.end - s.start), 0);

/** One clip as the view lists it (AGENTS.md §3). */
export function clipRow(clip, now, progress = null) {
  const end = clip.endedTs ?? now;
  const hidden = visibilitySpans(clip, clip.startedTs, end).filter((s) => !s.shown && s.reason !== 'unknown');
  const e = latestExport(clip);
  return {
    clip_id: clip.id,
    symbol: clip.symbol,
    origin: clip.origin,
    picture: clip.picture,
    started_ts: clip.startedTs,
    ended_ts: clip.endedTs,
    length_sec: Math.max(0, Math.round((end - clip.startedTs) * 10) / 10),
    status: clipStatus(clip),
    hq_sec: Math.round(sum(hqSpans(clip, now).map((s) => ({ start: Math.max(s.start, clip.startedTs), end: Math.min(s.end, end) })))),
    hidden_sec: Math.round(sum(hidden)),
    gap_sec: Math.round(sum(restartGaps(clip))),
    export: e
      ? {
          export_id: e.exportId,
          state: e.state,
          file: e.file,
          bytes: e.bytes,
          error: e.error,
          note: e.note,
          progress: e.state === 'running' ? progress : null,
          picture: e.settings?.picture ?? null,
          blur: Array.isArray(e.settings?.blur) ? e.settings.blur : [],
        }
      : null,
  };
}
