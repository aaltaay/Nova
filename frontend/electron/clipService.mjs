/**
 * Share clips (ADR 039): the clip supervisor in the main process. A clip is
 * marks on the always-on screen recording (ADR 035): it opens and closes on
 * the operator's word, and while it is open this module marks where its
 * Trader tab is (`geometry`) and whether it shows (`shown` / `hidden`),
 * starts and restarts its high-quality capture (clipHq.mjs, at most
 * CLIP_HQ_MAX_CONCURRENT, each CLIP_HQ_MAX_SEC), and beats once a minute so a
 * restart can say how long Nova was down. A quit never closes a clip: the next
 * start marks the gap and goes on; High quality does not restart by itself.
 * Exports run in clipExporter.mjs. `view()` is the one status every reader
 * gets (clipBridge.mjs); its shape is in AGENTS.md §3, "Share clips".
 *
 * maintainer: one-concern the clip lifecycle and its marks -- one owner for what a clip saw and when
 */
import fs from 'node:fs';
import path from 'node:path';
import * as P from './clipPlan.mjs';
import { clipRow, isOpen } from './clipManifest.mjs';
import { startClipExporter } from './clipExporter.mjs';
import { startClipHq } from './clipHq.mjs';
import { freePath, openClipStore } from './clipStore.mjs';
import { createTabTracker, geometryKey } from './clipTabs.mjs';
import { makeClipActions } from './clipServiceActions.mjs';
import { freeBytes, writableDir } from './screenRecordFiles.mjs';

const WINDOW_EVENTS = ['move', 'resize', 'minimize', 'restore', 'show', 'hide'];

export function startClipService({
  BrowserWindow,
  screen,
  ipcMain,
  shell,
  userData,
  exportPage,
  screenView = () => null,
  env = process.env,
  onView = () => {},
  logger = console,
  now = () => Date.now(),
  timers = globalThis,
  dataDriveMounted = () => fs.existsSync(P.CLIP_DATA_DRIVE),
}) {
  const sec = (ms = now()) => Math.round(ms) / 1000;
  let target = (() => {
    const first = P.resolveClipDir({ env, dataDriveMounted: dataDriveMounted(), userData, join: path.join });
    const error = writableDir(first.dir);
    if (!error || first.source === 'fallback') return { ...first, error };
    const fallback = P.resolveClipDir({ env: {}, dataDriveMounted: false, userData, join: path.join });
    const note = `${first.dir} cannot be written (${error}), so clips go to ${fallback.dir}`;
    logger.warn(`[nova] clips: ${note}`);
    return { ...fallback, note, error: writableDir(fallback.dir) };
  })();
  const store = openClipStore(target.dir, { logger });
  const tabs = createTabTracker({ screen, now });
  const live = new Map(); // clip id -> {windowId, shown, hiddenKey, geomKey, hqFailures, hqRetryAt, hqLost, hqError}
  const progress = new Map(); // export id -> {doneSec, duration}
  const watched = new WeakSet();
  let disk = { free: null, error: null, checked: 0 };
  let lastBeat = 0;
  let stopped = false;
  let dirty = true;

  const append = (row) => {
    store.append({ ts: sec(), ...row });
    dirty = true;
  };
  const liveFor = (id) => {
    if (!live.has(id)) live.set(id, { windowId: null, shown: null, hiddenKey: null, geomKey: null, hqFailures: 0, hqRetryAt: 0, hqLost: false, hqError: null });
    return live.get(id);
  };
  const openClips = () => [...store.clips().values()].filter(isOpen);

  // A restart: every open clip marks how long Nova was down; High quality ended with the old process.
  for (const clip of openClips()) {
    append({ event: 'mark', clip_id: clip.id, kind: 'restart', detail: { down_since: clip.lastBeatTs } });
    for (const s of clip.hq) if (s.end === null) append({ event: 'hq', clip_id: clip.id, state: 'end', file: s.file, reason: 'restart' });
    if (clip.hqWanted) append({ event: 'set', clip_id: clip.id, hq: false, reason: 'restart' });
  }
  for (const clip of store.clips().values()) {
    for (const e of clip.exports.values()) {
      if (e.state === 'queued' || e.state === 'running') {
        append({ event: 'export', clip_id: clip.id, export_id: e.exportId, state: 'failed', error: 'Nova closed while exporting', file: e.file });
      }
    }
  }

  const displayRecording = (displayId) => {
    const v = screenView();
    if (!v || !displayId) return null;
    const d = (v.displays || []).find((x) => String(x.id) === String(displayId));
    return d ? d.recording === true : false;
  };

  const hq = startClipHq({
    BrowserWindow,
    ipcMain,
    logger,
    now,
    openFile: (capture, mime) => {
      fs.mkdirSync(path.join(target.dir, P.CLIP_HQ_SUBDIR), { recursive: true });
      const where = freePath(path.join(target.dir, P.CLIP_HQ_SUBDIR), (n) => P.hqRelPath(now(), capture.symbol, mime, n));
      return { full: where.full, rel: `${P.CLIP_HQ_SUBDIR}/${where.rel}` };
    },
    onStarted: (clipId, info) => {
      const l = liveFor(clipId);
      Object.assign(l, { hqFailures: 0, hqLost: false, hqError: null });
      append({ event: 'hq', clip_id: clipId, state: 'start', file: info.rel, window_id: info.windowId });
    },
    onEnded: (clipId, info) => {
      append({ event: 'hq', clip_id: clipId, state: 'end', file: info.rel, reason: info.reason, error: info.error });
      if (info.reason === 'error') noteHqLoss(clipId, info.error);
    },
    onFailed: (clipId, info) => noteHqLoss(clipId, info.error),
  });

  function noteHqLoss(clipId, error) {
    const l = liveFor(clipId);
    l.hqFailures += 1;
    l.hqRetryAt = now() + P.retryDelayMs(l.hqFailures);
    l.hqLost = true;
    l.hqError = error ?? 'the capture stopped';
    dirty = true;
    logger.warn(`[nova] clip ${clipId} high quality lost: ${l.hqError}`);
  }

  const exporter = startClipExporter({
    BrowserWindow,
    ipcMain,
    page: exportPage,
    logger,
    now,
    onProgress: (job, doneSec) => {
      if (!progress.has(job.exportId)) {
        append({ event: 'export', clip_id: job.clipId, export_id: job.exportId, state: 'running', file: job.outRel });
      }
      progress.set(job.exportId, { doneSec, duration: job.duration });
      dirty = true;
    },
    onFinished: (job, res) => {
      progress.delete(job.exportId);
      append({
        event: 'export',
        clip_id: job.clipId,
        export_id: job.exportId,
        state: res.ok ? 'done' : res.cancelled ? 'cancelled' : 'failed',
        file: job.outRel,
        bytes: res.bytes,
        error: res.ok ? null : res.error,
      });
    },
  });

  function ensureHq(clip, l) {
    const running = hq.active(clip.id);
    if (!isOpen(clip) || !clip.hqWanted) {
      if (running) hq.stop(clip.id, clip.endedTs === null ? 'operator' : 'clip_closed');
      return;
    }
    const win = l.windowId ? tabs.windowOf(l.windowId) : null;
    if (!win || win.isDestroyed()) return;
    if (running && running.windowId === l.windowId) return;
    if (!running && now() < l.hqRetryAt) return;
    try {
      const b = win.getBounds();
      const scale = screen.getDisplayMatching?.(b)?.scaleFactor ?? 1;
      hq.start(clip.id, {
        sourceId: win.getMediaSourceId(),
        windowId: l.windowId,
        symbol: clip.symbol,
        plan: P.hqPlan(Math.round(b.width * scale), Math.round(b.height * scale)),
      });
    } catch (err) {
      noteHqLoss(clip.id, err instanceof Error ? err.message : String(err));
    }
  }

  /** Mark where the clip's tab is now: shown (with its geometry when it changed) or hidden, and why. */
  /** Mark where the clip's tab is now; `at` stamps the marks (a new clip's are at its start). */
  function evaluate(clip, at = null) {
    const l = liveFor(clip.id);
    const st = tabs.stateFor(clip.symbol, l.windowId);
    const stamp = at === null ? {} : { ts: at };
    if (st.shown) {
      if (l.shown !== true) append({ ...stamp, event: 'mark', clip_id: clip.id, kind: 'shown', detail: { window_id: st.windowId } });
      const gk = geometryKey(st.geometry);
      if (gk !== l.geomKey && st.geometry) append({ ...stamp, event: 'mark', clip_id: clip.id, kind: 'geometry', detail: st.geometry });
      Object.assign(l, { shown: true, hiddenKey: null, geomKey: gk, windowId: st.windowId });
    } else {
      const hk = JSON.stringify([st.reason, st.showing]);
      if (l.shown !== false || l.hiddenKey !== hk) {
        append({ ...stamp, event: 'mark', clip_id: clip.id, kind: 'hidden', detail: { reason: st.reason, showing: st.showing } });
      }
      Object.assign(l, { shown: false, hiddenKey: hk, windowId: st.windowId ?? l.windowId });
    }
    ensureHq(clip, l);
  }

  const evaluateAll = () => {
    for (const clip of openClips()) evaluate(clip);
  };

  function watchWindow(win) {
    if (watched.has(win)) return;
    watched.add(win);
    const refresh = () => {
      if (!stopped && tabs.refresh(win)) evaluateAll();
    };
    for (const name of WINDOW_EVENTS) win.on(name, refresh);
    const id = win.webContents.id;
    win.once('closed', () => {
      tabs.forget(id);
      if (!stopped) evaluateAll();
    });
  }

  function view() {
    const t = sec();
    const open = openClips().map((clip) => {
      const l = liveFor(clip.id);
      const st = tabs.stateFor(clip.symbol, l.windowId);
      const running = hq.active(clip.id);
      const screenOk = displayRecording(st.geometry?.display_id ?? null);
      let state = 'ok';
      if (!st.shown) state = 'hidden';
      else if (clip.hqWanted && l.hqLost) state = 'hq_lost';
      else if (!running && screenOk === false) state = 'no_picture';
      return {
        clip_id: clip.id,
        symbol: clip.symbol,
        started_ts: clip.startedTs,
        state,
        reason: st.shown ? null : st.reason,
        showing: st.showing ?? null,
        window_id: l.windowId,
        screen_recording: screenOk,
        hq: clip.hqWanted
          ? {
              since: clip.hqSince,
              ends_at: clip.hqSince === null ? null : clip.hqSince + P.CLIP_HQ_MAX_SEC,
              recording: Boolean(running?.startedAt),
              lost: l.hqLost,
              error: l.hqError,
              retry_at: l.hqLost && l.hqRetryAt ? sec(l.hqRetryAt) : null,
            }
          : null,
      };
    });
    const clips = [...store.clips().values()]
      .filter((c) => !c.deleted)
      .sort((a, b) => b.startedTs - a.startedTs)
      .slice(0, P.CLIP_VIEW_MAX)
      .map((c) => {
        const e = [...c.exports.values()].find((x) => progress.has(x.exportId));
        const p = e ? progress.get(e.exportId) : null;
        return clipRow(c, t, p && p.duration > 0 ? Math.min(1, p.doneSec / p.duration) : null);
      });
    const job = exporter.running();
    const jp = job ? progress.get(job.exportId) : null;
    return {
      schema_version: P.CLIP_SCHEMA_VERSION,
      generated_at: t,
      dir: target.dir,
      dir_source: target.source,
      dir_note: target.note,
      dir_error: store.error() ?? target.error ?? null,
      skipped: store.skipped(),
      hq_max: P.CLIP_HQ_MAX_CONCURRENT,
      hq_in_use: hq.count(),
      hq_max_sec: P.CLIP_HQ_MAX_SEC,
      hq_warn_sec: P.CLIP_HQ_WARN_SEC,
      last_n_sec: P.CLIP_LAST_N_SEC,
      open,
      clips,
      exporting: job ? { export_id: job.exportId, clip_id: job.clipId, done_sec: jp?.doneSec ?? 0, duration: job.duration } : null,
      queued: exporter.queued().length,
      tabs: tabs.entries().map((e) => ({
        window_id: e.windowId,
        symbol: e.symbol,
        visible: e.visible && !e.minimized,
        display_id: e.displayId,
        screen_recording: displayRecording(e.displayId),
      })),
      disk: { free_bytes: disk.free, state: diskState(disk.free), error: disk.error },
    };
  }

  const diskState = (free) => (typeof free !== 'number' ? 'unknown' : free < 10 * 1024 ** 3 ? 'fail' : free < 50 * 1024 ** 3 ? 'warn' : 'ok');
  const publish = () => {
    dirty = false;
    try {
      onView(view());
    } catch (err) {
      logger.warn(`[nova] clips view not published: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  function tick() {
    if (stopped) return;
    hq.tick();
    exporter.tick();
    const t = now();
    for (const clip of openClips()) {
      if (clip.hqWanted && clip.hqSince !== null && t / 1000 - clip.hqSince >= P.CLIP_HQ_MAX_SEC) {
        append({ event: 'set', clip_id: clip.id, hq: false, reason: 'limit' });
        hq.stop(clip.id, 'limit');
      }
      ensureHq(clip, liveFor(clip.id));
    }
    const ids = openClips().map((c) => c.id);
    if (ids.length && t - lastBeat >= P.CLIP_BEAT_MS) {
      lastBeat = t;
      append({ event: 'beat', clip_ids: ids });
    }
    if (t - disk.checked > 60_000) {
      disk.checked = t;
      void freeBytes(target.dir).then((d) => {
        disk = { ...disk, free: d.free, error: d.error };
        dirty = true;
      });
    }
    if (dirty || ids.length || exporter.running()) publish();
  }

  const actions = makeClipActions({
    store, tabs, hq, exporter, shell, screenView, displayRecording, evaluate, liveFor, append, now, sec,
    dir: () => target.dir,
    publish: () => { dirty = true; },
  });

  const interval = timers.setInterval(tick, P.CLIP_WATCH_MS);
  interval.unref?.();
  publish();

  return {
    view,
    isClipWindow: (w) => hq.isWindow(w) || exporter.isWindow(w),
    /** A desk window's Trader tab report (clipBridge.mjs checks the sender). */
    tabReport(win, report) {
      if (stopped || !win || win.isDestroyed()) return;
      watchWindow(win);
      if (tabs.report(win, report)) {
        evaluateAll();
        publish();
      }
    },
    act: async (request) => {
      const res = await actions.act(request);
      publish();
      return res;
    },
    stop(reason = 'quit') {
      if (stopped) return;
      stopped = true;
      timers.clearInterval(interval);
      hq.shutdown(reason);
      exporter.shutdown();
      publish();
    },
  };
}
