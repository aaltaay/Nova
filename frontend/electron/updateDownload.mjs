/**
 * Resumable installer download for in-app updates (#347).
 *
 * electron-updater fetches the ~150 MB installer as one request and starts
 * over from zero on any network error. On a link that corrupts one TLS record
 * every few dozen MB it never finishes (2026-09-23: v959 -> v961 failed with
 * net::ERR_SSL_PROTOCOL_ERROR on every attempt, while 6 GB over loopback TLS
 * on the same PC was clean). This fetches the same file in Range chunks,
 * retries each chunk on its own, keeps what arrived across failures and
 * restarts, checks the release's sha512, then hands the file to electron-updater
 * through its pending cache. electron-updater hashes the cached file again
 * before it offers Restart to update, so a bad file can never be installed.
 *
 * Persisted state: `<cacheDir>/nova-partial/<installer>.part` plus
 * `<installer>.part.json` (`schema_version` 1: version, sha512, size).
 * Owner: this module. Invalidation: a different sha512 or size (a newer release),
 * an unknown schema_version, a part longer than the file, or a finished file
 * whose sha512 does not match -- each discards the part and starts from zero.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';

export const UPDATE_CHUNK_BYTES = 8 * 1024 * 1024;
/** One chunk must arrive within this; a stalled connection is retried, not waited on forever. */
export const UPDATE_CHUNK_TIMEOUT_MS = 120_000;
/** Wait before each retry of the same chunk; the length is the retry budget (about 4 minutes). */
export const UPDATE_CHUNK_RETRY_DELAYS_MS = Object.freeze([1_000, 3_000, 10_000, 30_000, 60_000, 120_000]);
export const PARTIAL_DIR_NAME = 'nova-partial';
export const PARTIAL_SCHEMA_VERSION = 1;
/** A file another process holds open (antivirus, the Explorer preview) is retried this long. */
export const BUSY_RETRY_TRIES = 60;
export const BUSY_RETRY_INTERVAL_MS = 500;
const BUSY_CODES = new Set(['EBUSY', 'EPERM', 'EACCES']);
/** electron-updater's own names inside its cache dir (DownloadedUpdateHelper). */
const PENDING_DIR_NAME = 'pending';
const PENDING_INFO_FILE = 'update-info.json';

/** An error that no retry can fix (the release changed, the file is gone). */
class FatalDownloadError extends Error {}

/**
 * The installer electron-updater would download, from `provider.resolveFiles(info)`.
 * Null when anything needed for a checked, resumable download is missing.
 * @param {{ url: URL, info: { sha512?: string, size?: number, isAdminRightsRequired?: boolean } }[]} files
 * @param {string} version
 */
export function installerTarget(files, version) {
  const file = (Array.isArray(files) ? files : []).find(
    (f) => f?.url instanceof URL && decodeURIComponent(f.url.pathname).toLowerCase().endsWith('.exe'),
  );
  const size = Number(file?.info?.size);
  if (!file || !file.info.sha512 || !Number.isSafeInteger(size) || size <= 0) return null;
  return {
    url: file.url.href,
    // Same name electron-updater gives the file in its cache.
    fileName: path.basename(decodeURIComponent(file.url.pathname)),
    sha512: String(file.info.sha512),
    size,
    isAdminRightsRequired: file.info.isAdminRightsRequired === true,
    version: String(version ?? ''),
  };
}

/** Inclusive byte range of the next chunk, or null when the file is complete. */
export function nextRange(have, size, chunkBytes = UPDATE_CHUNK_BYTES) {
  if (have >= size) return null;
  return { start: have, end: Math.min(have + chunkBytes, size) - 1 };
}

/** `bytes 0-99/1000` -> {start, end, total}; anything else -> null. */
export function parseContentRange(header) {
  const m = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(String(header ?? '').trim());
  return m ? { start: Number(m[1]), end: Number(m[2]), total: Number(m[3]) } : null;
}

/** Delay before retry number `failures` (1-based) of one chunk, or null once the budget is spent. */
export function retryDelay(failures, delays = UPDATE_CHUNK_RETRY_DELAYS_MS) {
  return failures >= 1 && failures <= delays.length ? delays[failures - 1] : null;
}

/**
 * Run a file operation, waiting out a Windows sharing lock the way electron-updater
 * does for its own rename (60 x 500 ms). Any other error, or a lock that outlasts
 * the wait, is thrown.
 */
export async function retryWhileBusy(op, sleep, tries = BUSY_RETRY_TRIES, intervalMs = BUSY_RETRY_INTERVAL_MS) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await op();
    } catch (err) {
      if (!BUSY_CODES.has(err?.code) || attempt >= tries) throw err;
      await sleep(intervalMs);
    }
  }
}

function retryableStatus(status) {
  return status === 408 || status === 429 || status >= 500;
}

async function fetchRange(fetchImpl, target, range, timeoutMs) {
  const res = await fetchImpl(target.url, {
    headers: { Range: `bytes=${range.start}-${range.end}` },
    signal: AbortSignal.timeout(timeoutMs),
  });
  const want = range.end - range.start + 1;
  if (res.status === 206) {
    const got = parseContentRange(res.headers.get('content-range'));
    if (!got || got.total !== target.size) {
      throw new FatalDownloadError(`server file changed (Content-Range ${res.headers.get('content-range')})`);
    }
    if (got.start !== range.start || got.end !== range.end) {
      throw new Error(`server sent bytes ${got.start}-${got.end}, asked for ${range.start}-${range.end}`);
    }
  } else if (res.status === 200 && range.start === 0 && want === target.size) {
    // A server that ignores Range sends the whole file; fine when that was the ask.
  } else if (retryableStatus(res.status)) {
    throw new Error(`HTTP ${res.status}`);
  } else {
    throw new FatalDownloadError(`HTTP ${res.status} for ${target.fileName}`);
  }
  const body = Buffer.from(await res.arrayBuffer());
  if (body.length !== want) throw new Error(`short chunk: ${body.length} of ${want} bytes`);
  return body;
}

async function fileSize(file) {
  try {
    return (await fsp.stat(file)).size;
  } catch (err) {
    if (err?.code === 'ENOENT') return 0;
    throw err;
  }
}

async function sha512Base64(file) {
  const hash = crypto.createHash('sha512');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  return hash.digest('base64');
}

async function discardPartial(partFile, metaFile) {
  await fsp.rm(partFile, { force: true });
  await fsp.rm(metaFile, { force: true });
}

/** Bytes of this installer already on disk, after discarding anything stale. */
async function resumeOffset(partFile, metaFile, target, logger) {
  let meta = null;
  try {
    meta = JSON.parse(await fsp.readFile(metaFile, 'utf8'));
  } catch (err) {
    if (err?.code !== 'ENOENT') logger.warn(`partial download record unreadable, starting over: ${err.message}`);
  }
  const matches =
    meta?.schema_version === PARTIAL_SCHEMA_VERSION && meta.sha512 === target.sha512 && meta.size === target.size;
  const have = matches ? await fileSize(partFile) : 0;
  if (!matches || have > target.size) {
    if (meta && meta.schema_version !== PARTIAL_SCHEMA_VERSION) {
      logger.warn(`partial download record has schema_version ${meta.schema_version}; starting over`);
    }
    await discardPartial(partFile, metaFile);
    const record = { schema_version: PARTIAL_SCHEMA_VERSION, version: target.version, sha512: target.sha512, size: target.size };
    await fsp.writeFile(metaFile, JSON.stringify(record));
    return 0;
  }
  return have;
}

/**
 * The installer already handed off for this release (the operator chose Later
 * and restarted), or null. Size and recorded sha512 only: electron-updater
 * hashes the file itself before it offers Restart to update.
 */
async function alreadyPending(cacheDir, target) {
  const pendingDir = path.join(cacheDir, PENDING_DIR_NAME);
  try {
    const info = JSON.parse(await fsp.readFile(path.join(pendingDir, PENDING_INFO_FILE), 'utf8'));
    const file = path.join(pendingDir, target.fileName);
    if (info?.sha512 === target.sha512 && info.fileName === target.fileName && (await fileSize(file)) === target.size) {
      return file;
    }
  } catch {
    // No record, or not ours to read: download as usual.
  }
  return null;
}

/** Put the finished installer where electron-updater's cache check looks for it. */
async function handOff(partFile, metaFile, target, cacheDir, sleep) {
  const pendingDir = path.join(cacheDir, PENDING_DIR_NAME);
  // electron-updater owns this folder and empties it whenever it holds another version.
  // A file there can be held for a moment (antivirus scanning a new .exe); on failure
  // the verified part stays in nova-partial and the next attempt hands it off again.
  await retryWhileBusy(() => fsp.rm(pendingDir, { recursive: true, force: true }), sleep);
  await fsp.mkdir(pendingDir, { recursive: true });
  const finalFile = path.join(pendingDir, target.fileName);
  await retryWhileBusy(() => fsp.rename(partFile, finalFile), sleep);
  await fsp.rm(metaFile, { force: true });
  const info = { fileName: target.fileName, sha512: target.sha512, isAdminRightsRequired: target.isAdminRightsRequired };
  await fsp.writeFile(path.join(pendingDir, PENDING_INFO_FILE), JSON.stringify(info));
  return finalFile;
}

/**
 * Download `target` into electron-updater's cache under `cacheDir`, resuming any
 * earlier part. Resolves with the installer's path; rejects once one chunk has
 * used its whole retry budget, keeping the part for the next attempt.
 * @param {{ target: ReturnType<typeof installerTarget>, cacheDir: string, fetch: typeof fetch,
 *   logger: { info: Function, warn: Function }, onProgress?: (percent: number) => void,
 *   onRetry?: (r: { attempt: number, delayMs: number, message: string }) => void,
 *   sleep?: (ms: number) => Promise<void>, chunkBytes?: number, timeoutMs?: number }} opts
 */
export async function downloadInstaller(opts) {
  const { target, cacheDir, logger } = opts;
  const sleep = opts.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  const chunkBytes = opts.chunkBytes ?? UPDATE_CHUNK_BYTES;
  const timeoutMs = opts.timeoutMs ?? UPDATE_CHUNK_TIMEOUT_MS;
  const pending = await alreadyPending(cacheDir, target);
  if (pending) {
    logger.info(`${target.fileName} is already downloaded (${pending})`);
    opts.onProgress?.(100);
    return pending;
  }
  const partialDir = path.join(cacheDir, PARTIAL_DIR_NAME);
  await fsp.mkdir(partialDir, { recursive: true });
  const partFile = path.join(partialDir, `${target.fileName}.part`);
  const metaFile = `${partFile}.json`;

  let have = await resumeOffset(partFile, metaFile, target, logger);
  logger.info(`downloading ${target.fileName} (${target.size} bytes)${have ? `, resuming at ${have}` : ''}`);
  opts.onProgress?.((have / target.size) * 100);
  let failures = 0;
  for (let range = nextRange(have, target.size, chunkBytes); range; range = nextRange(have, target.size, chunkBytes)) {
    try {
      const body = await fetchRange(opts.fetch, target, range, timeoutMs);
      await fsp.appendFile(partFile, body);
      have += body.length;
      failures = 0;
      opts.onProgress?.((have / target.size) * 100);
    } catch (err) {
      // Whatever reached the disk is the truth, even after a failed append.
      have = await fileSize(partFile);
      if (err instanceof FatalDownloadError) {
        await discardPartial(partFile, metaFile);
        throw err;
      }
      failures += 1;
      const delayMs = retryDelay(failures);
      const message = err instanceof Error ? err.message : String(err);
      if (delayMs == null) throw new Error(`${message} (gave up on bytes ${range.start}-${range.end}; ${have} kept)`);
      logger.warn(`chunk ${range.start}-${range.end} failed (${message}); retry ${failures} in ${delayMs} ms`);
      opts.onRetry?.({ attempt: failures, delayMs, message });
      await sleep(delayMs);
    }
  }

  const sha512 = await sha512Base64(partFile);
  if (sha512 !== target.sha512) {
    await discardPartial(partFile, metaFile);
    throw new Error(`downloaded ${target.fileName} does not match the release checksum; discarded`);
  }
  const finalFile = await handOff(partFile, metaFile, target, cacheDir, sleep);
  logger.info(`downloaded and verified ${finalFile}`);
  return finalFile;
}
