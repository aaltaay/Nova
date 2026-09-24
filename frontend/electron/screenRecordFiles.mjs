/**
 * The trading screen recording (ADR 035), on disk: one video file per monitor
 * per quarter hour, and a day manifest that says when each began and ended.
 *
 * `<dir>/<YYYY-MM-DD>/<HHMMSS>-screen<N>.mkv` (Eastern date and start time),
 * and `<dir>/<YYYY-MM-DD>/segments.jsonl`, one JSON object per line:
 * `{schema_version: 1, event: "start", segment_id, file, display, width,
 * height, fps, bps, mime, started_ts}` and `{schema_version: 1, event: "end",
 * segment_id, file, ended_ts, bytes, reason, error}` (epoch seconds). A start
 * with no end is a segment cut short by a crash or a power loss: the file
 * holds everything up to its last write. Nothing here deletes a recording.
 */
import fs from 'node:fs';
import path from 'node:path';
import {
  SCREEN_RECORD_MANIFEST,
  SCREEN_RECORD_SCHEMA_VERSION,
  segmentRelPath,
} from './screenRecordPlan.mjs';

const errLine = (err) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

/** Append one manifest line; a failure is returned, never thrown (the video matters more). */
export function appendManifest(dayDir, row) {
  try {
    fs.mkdirSync(dayDir, { recursive: true });
    fs.appendFileSync(
      path.join(dayDir, SCREEN_RECORD_MANIFEST),
      `${JSON.stringify({ schema_version: SCREEN_RECORD_SCHEMA_VERSION, ...row })}\n`,
    );
    return null;
  } catch (err) {
    return errLine(err);
  }
}

/** A path under `dir` for a segment starting at `startMs` that does not exist yet. */
export function newSegmentPath(dir, startMs, displayIndex, mime) {
  for (let attempt = 1; attempt < 100; attempt += 1) {
    const { date, name } = segmentRelPath(startMs, displayIndex, mime, attempt);
    const full = path.join(dir, date, name);
    if (!fs.existsSync(full)) return { dayDir: path.join(dir, date), file: full };
  }
  throw new Error(`no free file name for screen ${displayIndex} at ${startMs}`);
}

/**
 * One segment's file. `write` never throws: the first error is kept on
 * `error` and later writes are dropped, so the recorder can start the monitor
 * again into a new file.
 */
export class SegmentFile {
  constructor(file) {
    this.file = file;
    this.bytes = 0;
    this.error = null;
    fs.mkdirSync(path.dirname(file), { recursive: true });
    this.stream = fs.createWriteStream(file, { flags: 'wx' });
    this.stream.on('error', (err) => {
      this.error = this.error || errLine(err);
    });
  }

  write(chunk) {
    if (this.error || !chunk || !chunk.length) return;
    this.bytes += chunk.length;
    this.stream.write(chunk);
  }

  /** Resolves once every write is on disk (or failed); the byte count written. */
  close() {
    return new Promise((resolve) => {
      if (this.stream.closed || this.stream.destroyed) {
        resolve(this.bytes);
        return;
      }
      this.stream.end(() => resolve(this.bytes));
    });
  }
}

/** Free bytes on the volume holding `dir` (its nearest existing ancestor), or the reason it cannot be read. */
export async function freeBytes(dir) {
  let probe = dir;
  try {
    while (!fs.existsSync(probe)) {
      const up = path.dirname(probe);
      if (up === probe) break;
      probe = up;
    }
    const s = await fs.promises.statfs(probe);
    return { free: Number(s.bavail) * Number(s.bsize), error: null };
  } catch (err) {
    return { free: null, error: errLine(err) };
  }
}

/** True when the folder can be created and written. */
export function writableDir(dir) {
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.accessSync(dir, fs.constants.W_OK);
    return null;
  } catch (err) {
    return errLine(err);
  }
}
