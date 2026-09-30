/**
 * Share clips (ADR 039): the high-quality window captures. One hidden page
 * (clipRecorder.html, its own renderer process) encodes; this module owns the
 * files and the watchdog: a capture that does not start, stalls or ends by
 * itself is reported (`onEnded` / `onFailed`) so clipService.mjs can mark it
 * and start it again, and a crashed page is replaced on the next start.
 *
 * Electron, the clock and the timers are passed in, so it is testable without
 * an Electron runtime.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  CLIP_HQ_MIMES,
  CLIP_HQ_STALL_MS,
  CLIP_HQ_START_TIMEOUT_MS,
  CLIP_HQ_STOP_TIMEOUT_MS,
  CLIP_HQ_TIMESLICE_MS,
  retryDelayMs,
} from './clipPlan.mjs';
import { SegmentFile } from './screenRecordFiles.mjs';

export const CLIP_REC_CMD_CHANNEL = 'nova:clip-rec:cmd';
export const CLIP_REC_READY_CHANNEL = 'nova:clip-rec:ready';
export const CLIP_REC_CHUNK_CHANNEL = 'nova:clip-rec:chunk';
export const CLIP_REC_EVENT_CHANNEL = 'nova:clip-rec:event';

const here = path.dirname(fileURLToPath(import.meta.url));
export const CLIP_RECORDER_PAGE = path.join(here, 'clipRecorder.html');
const PRELOAD = path.join(here, 'clipRecorderPreload.cjs');
const errLine = (err) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

export function startClipHq({
  BrowserWindow,
  ipcMain,
  openFile,
  onStarted = () => {},
  onEnded = () => {},
  onFailed = () => {},
  logger = console,
  now = () => Date.now(),
  pagePath = CLIP_RECORDER_PAGE,
}) {
  const windows = new WeakSet();
  const captures = new Map(); // capture id -> capture
  let win = null;
  let ready = false;
  let stopped = false;
  let pageFailures = 0;
  let pageRetryAt = 0;
  let seq = 0;

  const sec = (ms) => Math.round(ms) / 1000;
  const byClip = (clipId) => [...captures.values()].find((c) => c.clipId === clipId && !c.stopping) ?? null;

  function send(cmd) {
    if (!win || win.isDestroyed() || !ready) return false;
    win.webContents.send(CLIP_REC_CMD_CHANNEL, cmd);
    return true;
  }

  function sendStart(c) {
    c.sent = send({
      cmd: 'start',
      id: c.id,
      sourceId: c.sourceId,
      ...c.plan,
      mimes: [...CLIP_HQ_MIMES],
      timesliceMs: CLIP_HQ_TIMESLICE_MS,
    });
  }

  async function finalize(c, reason, error = null) {
    if (c.closed) return;
    c.closed = true;
    captures.delete(c.id);
    if (!c.startedAt) {
      onFailed(c.clipId, { reason: reason || 'error', error: error ?? c.error ?? 'the capture did not start' });
      return;
    }
    const bytes = c.file ? await c.file.close() : 0;
    onEnded(c.clipId, { rel: c.rel, reason: c.stopping || reason || 'error', error: c.stopError ?? error ?? c.file?.error ?? null, bytes, ts: sec(now()) });
  }

  function requestStop(c, reason, error = null) {
    if (c.stopping) return;
    c.stopping = reason;
    c.stopError = error;
    c.stopRequestedAt = now();
    if (!c.startedAt && !c.sent) {
      void finalize(c, reason, error);
      return;
    }
    send({ cmd: 'stop', id: c.id });
  }

  function onStartedEv(ev) {
    const c = captures.get(ev.id);
    if (!c || c.stopping) {
      send({ cmd: 'stop', id: ev.id });
      return;
    }
    try {
      const where = openFile(c, ev.mime);
      c.file = new SegmentFile(where.full);
      c.rel = where.rel;
    } catch (err) {
      c.error = `cannot write the capture: ${errLine(err)}`;
      requestStop(c, 'error', c.error);
      return;
    }
    c.startedAt = now();
    c.lastDataAt = c.startedAt;
    onStarted(c.clipId, { rel: c.rel, windowId: c.windowId, mime: ev.mime, ts: sec(c.startedAt) });
  }

  function onChunk(id, bytes) {
    const c = captures.get(id);
    if (!c || !c.startedAt) return;
    c.lastDataAt = now();
    if (!bytes || !c.file) return;
    c.file.write(Buffer.from(bytes.buffer ?? bytes, bytes.byteOffset ?? 0, bytes.byteLength ?? bytes.length));
    if (c.file.error && !c.stopping) requestStop(c, 'error', `writing the capture failed: ${c.file.error}`);
  }

  function onEvent(ev) {
    if (!ev || typeof ev !== 'object') return;
    const c = captures.get(ev.id);
    if (ev.kind === 'started') onStartedEv(ev);
    else if (ev.kind === 'stopped') {
      if (c) void finalize(c, c.stopping || 'error', ev.message || (c.stopping ? null : 'the capture stopped by itself'));
    } else if (ev.kind === 'error' && c) {
      const detail = String(ev.message || 'capture error');
      if (!c.startedAt) void finalize(c, 'error', detail);
      else requestStop(c, 'error', detail);
    }
  }

  function pageGone(page, why) {
    if (page !== win) return;
    win = null;
    ready = false;
    pageFailures += 1;
    pageRetryAt = now() + retryDelayMs(pageFailures);
    for (const c of [...captures.values()]) {
      c.stopping = c.stopping || 'error';
      c.stopError = c.stopError || why;
      void finalize(c, 'error', why);
    }
    logger.warn(`[nova] clip recorder page: ${why}`);
    if (!page.isDestroyed()) page.destroy();
  }

  function ensurePage() {
    if (stopped || win || now() < pageRetryAt) return;
    const page = new BrowserWindow({
      show: false,
      skipTaskbar: true,
      focusable: false,
      width: 320,
      height: 200,
      title: 'Nova clip recorder',
      webPreferences: {
        preload: PRELOAD,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        backgroundThrottling: false,
      },
    });
    windows.add(page);
    win = page;
    page.webContents.on('render-process-gone', (_e, details) =>
      pageGone(page, `the clip recorder process ended (${details?.reason ?? 'unknown'})`));
    page.on('closed', () => {
      if (!stopped) pageGone(page, 'the clip recorder window closed');
    });
    Promise.resolve(page.loadFile(pagePath)).catch((err) => pageGone(page, `the clip recorder page did not load: ${errLine(err)}`));
  }

  const fromPage = (event) => Boolean(win) && !win.isDestroyed() && event?.sender === win.webContents;
  const onReady = (event) => {
    if (!fromPage(event)) return;
    ready = true;
    pageFailures = 0;
    for (const c of captures.values()) if (!c.sent && !c.stopping) sendStart(c);
  };
  const onChunkMsg = (event, msg) => {
    if (fromPage(event)) onChunk(msg?.id, msg?.bytes);
  };
  const onEventMsg = (event, ev) => {
    if (fromPage(event)) onEvent(ev);
  };
  ipcMain.on(CLIP_REC_READY_CHANNEL, onReady);
  ipcMain.on(CLIP_REC_CHUNK_CHANNEL, onChunkMsg);
  ipcMain.on(CLIP_REC_EVENT_CHANNEL, onEventMsg);

  return {
    isWindow: (w) => Boolean(w) && windows.has(w),
    /** The running (or starting) capture of a clip, else null. */
    active: byClip,
    count: () => new Set([...captures.values()].filter((c) => !c.stopping).map((c) => c.clipId)).size,
    /** Capture `sourceId` for the clip; a capture of another window is stopped first (`reason: "window"`). */
    start(clipId, { sourceId, windowId, symbol, plan }) {
      const current = byClip(clipId);
      if (current && current.sourceId === sourceId) return current.id;
      if (current) requestStop(current, 'window');
      const c = {
        id: `hq-${now()}-${++seq}`,
        clipId,
        sourceId,
        windowId,
        symbol,
        plan,
        requestedAt: now(),
        startedAt: null,
        lastDataAt: null,
        file: null,
        rel: null,
        stopping: null,
        stopError: null,
        stopRequestedAt: 0,
        closed: false,
        sent: false,
        error: null,
      };
      captures.set(c.id, c);
      ensurePage();
      if (ready) sendStart(c);
      return c.id;
    },
    stop(clipId, reason) {
      for (const c of [...captures.values()]) if (c.clipId === clipId) requestStop(c, reason);
    },
    tick() {
      if (stopped) return;
      if (captures.size) ensurePage();
      const t = now();
      for (const c of [...captures.values()]) {
        if (c.stopping) {
          if (t - c.stopRequestedAt > CLIP_HQ_STOP_TIMEOUT_MS) void finalize(c, c.stopping);
        } else if (!c.startedAt) {
          if (t - c.requestedAt > CLIP_HQ_START_TIMEOUT_MS) {
            send({ cmd: 'stop', id: c.id });
            void finalize(c, 'error', `the capture did not start within ${CLIP_HQ_START_TIMEOUT_MS / 1000} s`);
          }
        } else if (t - c.lastDataAt > CLIP_HQ_STALL_MS) {
          requestStop(c, 'error', `no video for ${CLIP_HQ_STALL_MS / 1000} s`);
        }
      }
    },
    /** Quitting: stop every capture and close its file; the last timeslice may not reach the disk. */
    shutdown(reason = 'quit') {
      if (stopped) return;
      for (const c of [...captures.values()]) {
        c.stopping = c.stopping || reason;
        send({ cmd: 'stop', id: c.id });
        if (c.file) c.file.stream.end();
        captures.delete(c.id);
        if (c.startedAt) onEnded(c.clipId, { rel: c.rel, reason, error: null, bytes: c.file?.bytes ?? 0, ts: sec(now()) });
      }
      stopped = true;
      ipcMain.removeListener(CLIP_REC_READY_CHANNEL, onReady);
      ipcMain.removeListener(CLIP_REC_CHUNK_CHANNEL, onChunkMsg);
      ipcMain.removeListener(CLIP_REC_EVENT_CHANNEL, onEventMsg);
      if (win && !win.isDestroyed()) win.destroy();
    },
  };
}
