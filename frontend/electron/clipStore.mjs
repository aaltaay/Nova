/**
 * Share clips (ADR 039), on disk: the clip manifest (`<clips dir>/clips.jsonl`,
 * folded by clipManifest.mjs) and the screen recording's segment manifests
 * (ADR 035's `<screen dir>/<date>/segments.jsonl`), which an export reads.
 * Writes never throw -- the failure is returned and kept, like the screen
 * recorder's manifest. Nothing here deletes a screen recording; `removeFile`
 * is only ever given a clip's own export or high-quality file.
 */
import fs from 'node:fs';
import path from 'node:path';
import { CLIP_MANIFEST, CLIP_SCHEMA_VERSION } from './clipPlan.mjs';
import { applyRow, foldRows, parseManifest } from './clipManifest.mjs';

const errLine = (err) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

export function openClipStore(dir, { logger = console } = {}) {
  const file = path.join(dir, CLIP_MANIFEST);
  let clips = new Map();
  let skipped = 0;
  let error = null;
  try {
    if (fs.existsSync(file)) {
      const { rows, bad } = parseManifest(fs.readFileSync(file, 'utf8'));
      const folded = foldRows(rows);
      clips = folded.clips;
      skipped = folded.skipped + bad;
      if (skipped) logger.warn(`[nova] clips: ${skipped} manifest line(s) in ${file} could not be read and were left out`);
    }
  } catch (err) {
    error = `the clip list could not be read: ${errLine(err)}`;
    logger.warn(`[nova] clips: ${error}`);
  }

  return {
    dir,
    file,
    clips: () => clips,
    get: (id) => clips.get(id) ?? null,
    skipped: () => skipped,
    error: () => error,
    /** Append one row (the schema version is stamped here) and fold it in; returns the write's failure or null. */
    append(row) {
      const full = { schema_version: CLIP_SCHEMA_VERSION, ...row };
      applyRow(clips, full);
      try {
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(file, `${JSON.stringify(full)}\n`);
        if (error?.startsWith('the clip list could not be written')) error = null;
        return null;
      } catch (err) {
        error = `the clip list could not be written: ${errLine(err)}`;
        logger.warn(`[nova] clips: ${error}`);
        return error;
      }
    },
  };
}

/** A path inside `dir` (relative in the manifest), or null when `rel` would leave it. */
export function resolveInside(dir, rel) {
  if (typeof rel !== 'string' || !rel || path.isAbsolute(rel)) return null;
  const full = path.resolve(dir, rel);
  const root = path.resolve(dir);
  return full === root || !full.startsWith(root + path.sep) ? null : full;
}

/** A free path `<dir>/<date>/<name>` from a name maker `(attempt) => {date, name}`. */
export function freePath(dir, make) {
  for (let attempt = 1; attempt < 100; attempt += 1) {
    const { date, name } = make(attempt);
    const rel = path.join(date, name);
    const full = path.join(dir, rel);
    if (!fs.existsSync(full) && !fs.existsSync(`${full}.part`)) return { rel: rel.split(path.sep).join('/'), full };
  }
  throw new Error('no free file name for the clip');
}

export function removeFile(full) {
  try {
    if (full && fs.existsSync(full)) fs.unlinkSync(full);
    return null;
  } catch (err) {
    return errLine(err);
  }
}

export function fileSize(full) {
  try {
    return fs.statSync(full).size;
  } catch {
    return null; // gone or unreadable: the caller says the source is missing
  }
}

/**
 * The screen segments recorded on `dates` under `screenDir`:
 * `[{file, startedTs, endedTs, display, width, height, mime}]`. A segment with
 * no end row is the one still recording (`recordingFiles` names it: it ends
 * now) or one cut short by a crash (it ends at the file's last write).
 */
export function readScreenSegments(screenDir, dates, { now, recordingFiles = [] } = {}) {
  const out = [];
  const live = new Set(recordingFiles.map((f) => String(f)));
  for (const date of dates) {
    const dayDir = path.join(screenDir, date);
    let text;
    try {
      text = fs.readFileSync(path.join(dayDir, 'segments.jsonl'), 'utf8');
    } catch {
      continue; // no recording that day: nothing to read
    }
    const byId = new Map();
    for (const row of parseManifest(text).rows) {
      if (!row || row.schema_version !== 1 || typeof row.segment_id !== 'string') continue;
      if (row.event === 'start' && typeof row.file === 'string' && row.display?.bounds) {
        byId.set(row.segment_id, {
          file: path.join(dayDir, row.file),
          name: row.file,
          startedTs: row.started_ts,
          endedTs: null,
          display: row.display,
          width: row.width,
          height: row.height,
          mime: row.mime ?? null,
        });
      } else if (row.event === 'end' && byId.has(row.segment_id)) {
        byId.get(row.segment_id).endedTs = row.ended_ts;
      }
    }
    for (const seg of byId.values()) {
      if (typeof seg.startedTs !== 'number') continue;
      let size;
      let mtime;
      try {
        const st = fs.statSync(seg.file);
        size = st.size;
        mtime = st.mtimeMs / 1000;
      } catch {
        continue; // the file is gone: it cannot be read
      }
      if (typeof seg.endedTs !== 'number') seg.endedTs = live.has(seg.name) ? now : mtime;
      if (size > 0 && seg.endedTs > seg.startedTs) out.push({ ...seg, size });
    }
  }
  return out.sort((a, b) => a.startedTs - b.startedTs);
}
