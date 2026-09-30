/**
 * Share clips (ADR 039): exports, one at a time, on a hidden page
 * (`clip-export.html`, built by Vite with WebCodecs + mediabunny). The page is
 * sandboxed: it reads the source files and writes the MP4 only through this
 * module, and only the files the job names -- each by a token, never a path
 * the page chose. The MP4 is written to `<name>.mp4.part` and renamed when the
 * page says it is done; a failure or a cancel removes the part file. The page
 * also draws single preview frames for the export dialog.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { retryDelayMs } from './clipPlan.mjs';

export const CLIP_EXPORT_JOB_CHANNEL = 'nova:clip-export:job';
export const CLIP_EXPORT_CANCEL_CHANNEL = 'nova:clip-export:cancel';
export const CLIP_EXPORT_PREVIEW_CHANNEL = 'nova:clip-export:preview';
export const CLIP_EXPORT_READY_CHANNEL = 'nova:clip-export:ready';
export const CLIP_EXPORT_READ_CHANNEL = 'nova:clip-export:read';
export const CLIP_EXPORT_WRITE_CHANNEL = 'nova:clip-export:write';
export const CLIP_EXPORT_PROGRESS_CHANNEL = 'nova:clip-export:progress';
export const CLIP_EXPORT_DONE_CHANNEL = 'nova:clip-export:done';
export const CLIP_EXPORT_PREVIEW_DONE_CHANNEL = 'nova:clip-export:preview-done';
/** A job that neither reads, writes nor reports for this long has stalled. */
export const CLIP_EXPORT_STALL_MS = 120_000;
export const CLIP_PREVIEW_TIMEOUT_MS = 30_000;
/** The page reads at most this much per call. */
const MAX_READ_BYTES = 32 * 1024 * 1024;

const here = path.dirname(fileURLToPath(import.meta.url));
const PRELOAD = path.join(here, 'clipExportPreload.cjs');
const errLine = (err) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

export function startClipExporter({
  BrowserWindow,
  ipcMain,
  page,
  onProgress = () => {},
  onFinished = () => {},
  logger = console,
  now = () => Date.now(),
}) {
  const windows = new WeakSet();
  const queue = [];
  const tokens = new Map(); // token -> { full, size, handle, owner }
  const previews = new Map(); // req id -> { resolve, timer, owner }
  let win = null;
  let ready = false;
  let stopped = false;
  let current = null;
  let pageFailures = 0;
  let pageRetryAt = 0;
  let seq = 0;

  function register(full, owner) {
    const token = `t${now()}-${++seq}`;
    const size = fs.statSync(full).size;
    tokens.set(token, { full, size, handle: null, owner });
    return { token, size };
  }

  async function releaseTokens(owner) {
    for (const [token, t] of [...tokens]) {
      if (t.owner !== owner) continue;
      tokens.delete(token);
      if (t.handle) await t.handle.close().catch((err) => logger.warn(`[nova] clip export: closing a source failed: ${errLine(err)}`));
    }
  }

  async function finish(job, ok, error) {
    if (job.finished) return;
    job.finished = true;
    if (current === job) current = null;
    await releaseTokens(job.id);
    let bytes = null;
    if (job.out) await job.out.close().catch((err) => { error = error ?? `closing the export failed: ${errLine(err)}`; ok = false; });
    if (ok) {
      try {
        fs.renameSync(job.part, job.outFull);
        bytes = fs.statSync(job.outFull).size;
      } catch (err) {
        ok = false;
        error = `the finished export could not be saved: ${errLine(err)}`;
      }
    }
    if (!ok) {
      try {
        if (fs.existsSync(job.part)) fs.unlinkSync(job.part);
      } catch (err) {
        logger.warn(`[nova] clip export: removing ${job.part} failed: ${errLine(err)}`);
      }
    }
    onFinished(job, { ok, error: ok ? null : error ?? 'the export failed', bytes, cancelled: job.cancelled });
    pump();
  }

  function send(channel, msg) {
    if (!win || win.isDestroyed() || !ready) return false;
    win.webContents.send(channel, msg);
    return true;
  }

  async function run(job) {
    current = job;
    job.lastActivity = now();
    try {
      fs.mkdirSync(path.dirname(job.part), { recursive: true });
      job.out = await fs.promises.open(job.part, 'w');
      const pieces = job.pieces.map((p) => {
        const { token, size } = register(p.file, job.id);
        return { token, size, kind: p.kind, t0: p.t0, t1: p.t1, out0: p.out0, crop: p.crop, blur: p.blur, window: p.window ?? null };
      });
      if (!send(CLIP_EXPORT_JOB_CHANNEL, { job_id: job.id, out: job.outSpec, duration: job.duration, pieces })) {
        throw new Error('the export page is not ready');
      }
      onProgress(job, 0);
    } catch (err) {
      await finish(job, false, errLine(err));
    }
  }

  function pump() {
    if (stopped || current || !queue.length) return;
    ensurePage();
    if (!ready) return;
    void run(queue.shift());
  }

  function pageGone(p, why) {
    if (p !== win) return;
    win = null;
    ready = false;
    pageFailures += 1;
    pageRetryAt = now() + retryDelayMs(pageFailures);
    if (current) void finish(current, false, why);
    for (const [id, pv] of [...previews]) {
      previews.delete(id);
      clearTimeout(pv.timer);
      void releaseTokens(pv.owner);
      pv.resolve({ ok: false, error: why });
    }
    logger.warn(`[nova] clip export page: ${why}`);
    if (!p.isDestroyed()) p.destroy();
  }

  function ensurePage() {
    if (stopped || win || now() < pageRetryAt) return;
    const p = new BrowserWindow({
      show: false,
      skipTaskbar: true,
      focusable: false,
      width: 320,
      height: 200,
      title: 'Nova clip export',
      webPreferences: { preload: PRELOAD, contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false },
    });
    windows.add(p);
    win = p;
    p.webContents.on('render-process-gone', (_e, details) => pageGone(p, `the export page ended (${details?.reason ?? 'unknown'})`));
    p.on('closed', () => {
      if (!stopped) pageGone(p, 'the export window closed');
    });
    const load = page.url ? p.loadURL(page.url) : p.loadFile(page.file);
    Promise.resolve(load).catch((err) => pageGone(p, `the export page did not load: ${errLine(err)}`));
  }

  const fromPage = (event) => Boolean(win) && !win.isDestroyed() && event?.sender === win.webContents;
  const onReady = (event) => {
    if (!fromPage(event)) return;
    ready = true;
    pageFailures = 0;
    pump();
  };
  const onRead = async (event, req) => {
    if (!fromPage(event)) throw new Error('not the export page');
    const t = tokens.get(req?.token);
    if (!t) throw new Error('unknown source');
    const start = Math.max(0, Number(req.start) || 0);
    const end = Math.min(t.size, Number(req.end) || 0, start + MAX_READ_BYTES);
    if (end <= start) return new Uint8Array(0);
    if (current && t.owner === current.id) current.lastActivity = now();
    if (!t.handle) t.handle = await fs.promises.open(t.full, 'r');
    const buf = Buffer.alloc(end - start);
    const { bytesRead } = await t.handle.read(buf, 0, end - start, start);
    return new Uint8Array(buf.buffer, buf.byteOffset, bytesRead);
  };
  const onWrite = async (event, req) => {
    if (!fromPage(event)) throw new Error('not the export page');
    if (!current || req?.job_id !== current.id || !current.out) throw new Error('no export is running');
    const data = req.data instanceof Uint8Array ? req.data : new Uint8Array(req.data ?? []);
    current.lastActivity = now();
    await current.out.write(data, 0, data.byteLength, Number(req.position) || 0);
    return true;
  };
  const onProgressMsg = (event, msg) => {
    if (!fromPage(event) || !current || msg?.job_id !== current.id) return;
    current.lastActivity = now();
    onProgress(current, Number(msg.done_sec) || 0);
  };
  const onDone = (event, msg) => {
    if (!fromPage(event) || !current || msg?.job_id !== current.id) return;
    void finish(current, msg.ok === true && !current.cancelled, current.cancelled ? 'cancelled' : msg.error);
  };
  const onPreviewDone = (event, msg) => {
    if (!fromPage(event)) return;
    const pv = previews.get(msg?.req_id);
    if (!pv) return;
    previews.delete(msg.req_id);
    clearTimeout(pv.timer);
    void releaseTokens(pv.owner);
    pv.resolve(msg.ok ? { ok: true, bytes: msg.bytes, width: msg.width, height: msg.height } : { ok: false, error: msg.error || 'no frame' });
  };
  ipcMain.on(CLIP_EXPORT_READY_CHANNEL, onReady);
  ipcMain.handle(CLIP_EXPORT_READ_CHANNEL, onRead);
  ipcMain.handle(CLIP_EXPORT_WRITE_CHANNEL, onWrite);
  ipcMain.on(CLIP_EXPORT_PROGRESS_CHANNEL, onProgressMsg);
  ipcMain.on(CLIP_EXPORT_DONE_CHANNEL, onDone);
  ipcMain.on(CLIP_EXPORT_PREVIEW_DONE_CHANNEL, onPreviewDone);

  return {
    isWindow: (w) => Boolean(w) && windows.has(w),
    running: () => current,
    queued: () => [...queue],
    /** Queue an export: `{id, clipId, exportId, pieces, outSpec, duration, outFull}`; the part file sits beside it. */
    enqueue(job) {
      queue.push({ ...job, part: `${job.outFull}.part`, finished: false, cancelled: false, out: null });
      pump();
    },
    cancel(exportId) {
      const q = queue.findIndex((j) => j.exportId === exportId);
      if (q >= 0) {
        const [job] = queue.splice(q, 1);
        job.cancelled = true;
        onFinished(job, { ok: false, error: 'cancelled', bytes: null, cancelled: true });
        return true;
      }
      if (current?.exportId === exportId) {
        current.cancelled = true;
        send(CLIP_EXPORT_CANCEL_CHANNEL, { job_id: current.id });
        return true;
      }
      return false;
    },
    /** One frame of `file` at `t` s, cropped: `{ok, bytes (JPEG), width, height}` or `{ok: false, error}`. */
    preview({ file, t, crop, out, blur, window: spec = null }) {
      return new Promise((resolve) => {
        ensurePage();
        const owner = `pv${now()}-${++seq}`;
        let token;
        let size;
        try {
          ({ token, size } = register(file, owner));
        } catch (err) {
          resolve({ ok: false, error: `the recording cannot be read: ${errLine(err)}` });
          return;
        }
        const timer = setTimeout(() => {
          previews.delete(owner);
          void releaseTokens(owner);
          resolve({ ok: false, error: 'the preview took too long' });
        }, CLIP_PREVIEW_TIMEOUT_MS);
        previews.set(owner, { resolve, timer, owner });
        const go = () => send(CLIP_EXPORT_PREVIEW_CHANNEL, { req_id: owner, token, size, t, crop, out, blur, window: spec });
        if (!go()) {
          // The page is loading: ask again once it is ready (the timeout covers a page that never is).
          const wait = setInterval(() => {
            if (!previews.has(owner)) clearInterval(wait);
            else if (go()) clearInterval(wait);
          }, 250);
        }
      });
    },
    tick() {
      if (current && now() - current.lastActivity > CLIP_EXPORT_STALL_MS) {
        void finish(current, false, `the export stalled (nothing for ${CLIP_EXPORT_STALL_MS / 1000} s)`);
        if (win && !win.isDestroyed()) win.destroy();
      }
      pump();
    },
    shutdown() {
      if (stopped) return;
      stopped = true;
      ipcMain.removeListener(CLIP_EXPORT_READY_CHANNEL, onReady);
      ipcMain.removeHandler?.(CLIP_EXPORT_READ_CHANNEL);
      ipcMain.removeHandler?.(CLIP_EXPORT_WRITE_CHANNEL);
      ipcMain.removeListener(CLIP_EXPORT_PROGRESS_CHANNEL, onProgressMsg);
      ipcMain.removeListener(CLIP_EXPORT_DONE_CHANNEL, onDone);
      ipcMain.removeListener(CLIP_EXPORT_PREVIEW_DONE_CHANNEL, onPreviewDone);
      if (current) {
        const job = current;
        current = null;
        job.finished = true;
        void job.out?.close();
        try {
          if (fs.existsSync(job.part)) fs.unlinkSync(job.part);
        } catch (err) {
          logger.warn(`[nova] clip export: removing ${job.part} failed: ${errLine(err)}`);
        }
        onFinished(job, { ok: false, error: 'Nova quit while exporting', bytes: null, cancelled: false });
      }
      if (win && !win.isDestroyed()) win.destroy();
    },
  };
}
