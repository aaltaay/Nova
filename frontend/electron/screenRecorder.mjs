/**
 * The trading screen recording (ADR 035, operator decision 2026-09-24:
 * "I always, always, always want the screen that I'm trading to be recorded
 * ... That's definitely not negotiable."). Every monitor, from the moment the
 * desktop app starts until it quits, with no switch to turn it off.
 *
 * maintainer: one-concern the never-leave-a-monitor-unrecorded supervisor -- starts, rotates, watches and restarts every capture
 *
 * The main process owns everything that decides: the plan per monitor
 * (screenRecordPlan.mjs), the files (screenRecordFiles.mjs) and this
 * supervisor. A hidden window (screenRecorder.html) only captures and encodes.
 * Resume, then say so: a monitor whose recording fails, stalls or disappears is
 * started again with backoff (never given up), a crashed recorder page is
 * replaced, a display change re-plans, and sleep pauses. A new file starts on
 * every quarter hour, and the new one is recording before the old one stops,
 * so rotation leaves no gap. `view()` is the one status every reader gets
 * (screenRecordBridge.mjs); its shape is in AGENTS.md §3.
 *
 * Electron, the clock and the timers are passed in (main.mjs) so this module
 * is testable without an Electron runtime.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as P from './screenRecordPlan.mjs';
import { SegmentFile, appendManifest, freeBytes, newSegmentPath, writableDir } from './screenRecordFiles.mjs';

export const SCREEN_REC_CMD_CHANNEL = 'nova:screen-rec:cmd';
export const SCREEN_REC_READY_CHANNEL = 'nova:screen-rec:ready';
export const SCREEN_REC_CHUNK_CHANNEL = 'nova:screen-rec:chunk';
export const SCREEN_REC_EVENT_CHANNEL = 'nova:screen-rec:event';
/** Before this, a monitor not yet recording reads "starting", not "failed". */
export const SCREEN_RECORD_START_GRACE_MS = 20_000;
/** A monitor the screen API did not list is looked for again this often. */
const REPLAN_UNMATCHED_MS = 60_000;

const here = path.dirname(fileURLToPath(import.meta.url));
export const SCREEN_RECORDER_PAGE = path.join(here, 'screenRecorder.html');
const PRELOAD = path.join(here, 'screenRecorderPreload.cjs');

const sec = (ms) => (ms == null ? null : Math.round(ms) / 1000);
const errLine = (err) => (err instanceof Error ? err.message : String(err ?? 'unknown error'));

export function startScreenRecorder({
  BrowserWindow,
  desktopCapturer,
  screen,
  powerMonitor = null,
  ipcMain,
  userData,
  env = process.env,
  onView = () => {},
  logger = console,
  now = () => Date.now(),
  timers = globalThis,
  dataDriveMounted = () => fs.existsSync(P.SCREEN_RECORD_DATA_DRIVE),
  segmentMs = P.SCREEN_RECORD_SEGMENT_MS,
  pagePath = SCREEN_RECORDER_PAGE,
}) {
  const startedAt = now();
  const recorderWindows = new WeakSet();
  const states = new Map(); // display id -> monitor state
  const segments = new Map(); // segment id -> segment
  let win = null;
  let ready = false;
  let stopped = false;
  let suspended = false;
  let pageFailures = 0;
  let pageRetryAt = 0;
  let pageError = null;
  let unmatched = [];
  let planError = null;
  let lastPlanAt = 0;
  let planSeq = 0;
  let seq = 0;
  let mime = null;
  let restarts = 0;
  let problems = [];
  let disk = { free: null, error: null, checked: 0 };
  let settleTimer = null;

  function resolveTarget() {
    const first = P.resolveRecordDir({ env, dataDriveMounted: dataDriveMounted(), userData, join: path.join });
    const error = writableDir(first.dir);
    if (!error || first.source === 'fallback') return { ...first, error };
    const fallback = P.resolveRecordDir({ env: {}, dataDriveMounted: false, userData, join: path.join });
    const why = `${first.dir} cannot be written (${error}), so the screen records to ${fallback.dir}`;
    logger.warn(`[nova] screen recording: ${why}`);
    return { ...fallback, note: why, error: writableDir(fallback.dir) };
  }
  let target = resolveTarget();

  const publish = () => {
    try {
      onView(view());
    } catch (err) {
      logger.warn(`[nova] screen recording view not published: ${errLine(err)}`);
    }
  };

  function send(cmd) {
    if (!win || win.isDestroyed() || !ready) return false;
    win.webContents.send(SCREEN_REC_CMD_CHANNEL, cmd);
    return true;
  }

  function addProblem(state, reason, detail) {
    problems = [
      { at: sec(now()), display_index: state.plan.display.index, reason, detail, resumed_at: null },
      ...problems,
    ].slice(0, P.SCREEN_RECORD_PROBLEMS_KEEP);
  }

  /** Run the watch as soon as a retry is due, not up to one watch interval later. */
  function wakeIn(ms) {
    const timer = timers.setTimeout(() => {
      if (!stopped) tick();
    }, ms + 5);
    timer.unref?.();
  }

  /** A monitor lost (or could not get) its recording: say so once, then retry with backoff, forever. */
  function noteFailure(state, reason, detail) {
    state.failures += 1;
    state.error = detail;
    state.retryAt = now() + P.retryDelayMs(state.failures);
    wakeIn(P.retryDelayMs(state.failures));
    if (state.since !== null || state.failures === 1) addProblem(state, reason, detail);
    state.since = null;
    restarts += 1;
    logger.warn(`[nova] screen ${state.plan.display.index} not recording (${reason}): ${detail}`);
  }

  function newState(plan) {
    return { plan, active: null, pending: null, failures: 0, retryAt: 0, rotateAt: 0, error: null, since: null };
  }

  function startSegment(state) {
    const { plan } = state;
    const seg = {
      id: `${now()}-${++seq}`,
      key: plan.key,
      plan,
      requestedAt: now(),
      startedAt: null,
      lastDataAt: null,
      file: null,
      dayDir: null,
      stopping: null,
      stopError: null,
      stopRequestedAt: 0,
      closed: false,
    };
    segments.set(seg.id, seg);
    state.pending = seg;
    send({
      cmd: 'start',
      id: seg.id,
      sourceId: plan.sourceId,
      width: plan.width,
      height: plan.height,
      fps: plan.fps,
      bps: plan.bps,
      mimes: [...P.SCREEN_RECORD_MIMES],
      timesliceMs: P.SCREEN_RECORD_TIMESLICE_MS,
    });
  }

  function stopSegment(seg, reason, error = null) {
    if (seg.stopping) return;
    seg.stopping = reason;
    seg.stopError = error;
    seg.stopRequestedAt = now();
    send({ cmd: 'stop', id: seg.id });
  }

  async function finalize(seg) {
    if (seg.closed) return;
    seg.closed = true;
    segments.delete(seg.id);
    const bytes = seg.file ? await seg.file.close() : 0;
    if (seg.dayDir) {
      const failed = appendManifest(seg.dayDir, {
        event: 'end',
        segment_id: seg.id,
        file: path.basename(seg.file.file),
        ended_ts: sec(now()),
        bytes,
        reason: seg.stopping || 'error',
        error: seg.stopError ?? seg.file?.error ?? null,
      });
      if (failed) logger.warn(`[nova] screen recording manifest not written: ${failed}`);
    }
    publish();
  }

  /** Every segment still open is closed now, synchronously -- the process is exiting. */
  function finalizeNow() {
    for (const seg of [...segments.values()]) {
      if (seg.closed) continue;
      seg.closed = true;
      segments.delete(seg.id);
      if (!seg.file) continue;
      seg.file.stream.end();
      appendManifest(seg.dayDir, {
        event: 'end',
        segment_id: seg.id,
        file: path.basename(seg.file.file),
        ended_ts: sec(now()),
        bytes: seg.file.bytes,
        reason: seg.stopping || 'quit',
        error: seg.stopError ?? seg.file.error ?? null,
      });
    }
  }

  function onStarted(ev) {
    const seg = segments.get(ev.id);
    if (!seg || seg.stopping) {
      send({ cmd: 'stop', id: ev.id }); // stopped (or forgotten) before it began: nothing to keep
      return;
    }
    const state = states.get(seg.key);
    if (!state || state.pending !== seg) {
      stopSegment(seg, 'display_change');
      return;
    }
    state.pending = null;
    const t = now();
    try {
      const where = newSegmentPath(target.dir, t, seg.plan.display.index, ev.mime);
      seg.file = new SegmentFile(where.file);
      seg.dayDir = where.dayDir;
    } catch (err) {
      stopSegment(seg, 'error', errLine(err));
      target = resolveTarget();
      if (state.active) state.retryAt = t + P.retryDelayMs(1);
      else noteFailure(state, 'error', `cannot write the recording: ${errLine(err)}`);
      publish();
      return;
    }
    mime = ev.mime;
    seg.startedAt = t;
    seg.lastDataAt = t;
    appendManifest(seg.dayDir, {
      event: 'start',
      segment_id: seg.id,
      file: path.basename(seg.file.file),
      display: seg.plan.display,
      width: ev.width ?? seg.plan.width,
      height: ev.height ?? seg.plan.height,
      fps: seg.plan.fps,
      bps: seg.plan.bps,
      mime: ev.mime,
      started_ts: sec(t),
    });
    const old = state.active;
    state.active = seg;
    state.rotateAt = P.nextBoundaryMs(t, segmentMs);
    state.failures = 0;
    state.error = null;
    if (old) {
      stopSegment(old, 'rotation'); // only now: the new file is already recording
    } else {
      if (state.since === null) state.since = t;
      for (const p of problems) {
        if (p.display_index === seg.plan.display.index && p.resumed_at === null) p.resumed_at = sec(t);
      }
      logger.info?.(`[nova] screen ${seg.plan.display.index} recording to ${seg.file.file}`);
    }
    publish();
  }

  function onChunk(id, bytes) {
    const seg = segments.get(id);
    if (!seg || !seg.startedAt) return;
    seg.lastDataAt = now();
    if (!bytes || !seg.file) return;
    seg.file.write(Buffer.from(bytes.buffer ?? bytes, bytes.byteOffset ?? 0, bytes.byteLength ?? bytes.length));
    if (seg.file.error && !seg.stopping) {
      const state = states.get(seg.key);
      stopSegment(seg, 'error', seg.file.error);
      target = resolveTarget();
      if (state?.active === seg) {
        state.active = null;
        noteFailure(state, 'error', `writing ${seg.file.file} failed: ${seg.file.error}`);
      }
      publish();
    }
  }

  function onStopped(ev) {
    const seg = segments.get(ev.id);
    if (!seg) return;
    if (!seg.stopping) {
      // Nobody asked: the capture ended by itself (a monitor unplugged, the screen lost).
      seg.stopping = 'error';
      seg.stopError = ev.message || 'the recording stopped by itself';
      const state = states.get(seg.key);
      if (state?.active === seg) {
        state.active = null;
        noteFailure(state, 'error', seg.stopError);
      }
      if (state?.pending === seg) state.pending = null;
      scheduleReplan();
    }
    void finalize(seg);
  }

  function onError(ev) {
    const seg = segments.get(ev.id);
    const detail = String(ev.message || 'recorder error');
    if (!seg) {
      logger.warn(`[nova] screen recorder: ${detail}`);
      return;
    }
    const state = states.get(seg.key);
    if (!seg.startedAt) {
      segments.delete(seg.id);
      if (state?.pending === seg) {
        state.pending = null;
        if (state.active) state.retryAt = now() + P.retryDelayMs(1); // a rotation that failed: the old file keeps going
        else noteFailure(state, 'error', detail);
      }
    } else if (state?.active === seg) {
      state.active = null;
      stopSegment(seg, 'error', detail);
      noteFailure(state, 'error', detail);
    } else if (!seg.stopError) {
      seg.stopError = detail;
    }
    publish();
  }

  function onEvent(ev) {
    if (!ev || typeof ev !== 'object') return;
    if (ev.kind === 'started') onStarted(ev);
    else if (ev.kind === 'stopped') onStopped(ev);
    else if (ev.kind === 'error') onError(ev);
  }

  function ensureAll() {
    if (stopped || suspended || !ready) return;
    const t = now();
    for (const state of states.values()) {
      if (state.pending || t < state.retryAt) continue;
      if (!state.active || t >= state.rotateAt) startSegment(state);
    }
  }

  async function replan(reason) {
    if (stopped || suspended || !ready) return;
    const token = ++planSeq;
    lastPlanAt = now();
    let sources;
    try {
      sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 0, height: 0 } });
    } catch (err) {
      planError = `Windows did not list the screens: ${errLine(err)}`;
      logger.warn(`[nova] screen recording (${reason}): ${planError}`);
      publish();
      return;
    }
    if (token !== planSeq || stopped || suspended) return;
    const { plans, unmatched: missing } = P.planDisplays({
      displays: screen.getAllDisplays(),
      sources,
      primaryId: screen.getPrimaryDisplay()?.id,
    });
    unmatched = missing;
    planError = plans.length ? null : 'Windows gave Nova no screen to capture';
    const next = new Map(plans.map((p) => [p.key, p]));
    for (const [key, state] of [...states]) {
      const plan = next.get(key);
      if (plan && P.samePlan(state.plan, plan)) {
        state.plan = plan;
        continue;
      }
      // The monitor changed or went away: what records the old picture stops, planned.
      for (const seg of [state.active, state.pending]) if (seg) stopSegment(seg, 'display_change');
      if (!plan) {
        states.delete(key);
        continue;
      }
      Object.assign(state, { plan, active: null, pending: null, failures: 0, retryAt: 0, error: null });
    }
    for (const [key, plan] of next) if (!states.has(key)) states.set(key, newState(plan));
    ensureAll();
    publish();
  }

  function scheduleReplan() {
    if (settleTimer) return;
    settleTimer = timers.setTimeout(() => {
      settleTimer = null;
      void replan('display');
    }, P.SCREEN_RECORD_DISPLAY_SETTLE_MS);
  }

  function pageGone(page, why) {
    if (page !== win) return;
    win = null;
    ready = false;
    pageError = why;
    pageFailures += 1;
    pageRetryAt = now() + P.retryDelayMs(pageFailures);
    wakeIn(P.retryDelayMs(pageFailures));
    for (const seg of [...segments.values()]) {
      const state = states.get(seg.key);
      if (state?.active === seg) {
        state.active = null;
        noteFailure(state, 'recorder_gone', why);
      }
      if (state?.pending === seg) state.pending = null;
      seg.stopping = seg.stopping || 'recorder_gone';
      seg.stopError = seg.stopError || why;
      void finalize(seg);
    }
    logger.warn(`[nova] screen recorder page: ${why}`);
    if (!page.isDestroyed()) page.destroy();
    publish();
  }

  function ensurePage() {
    if (stopped || win || now() < pageRetryAt) return;
    const page = new BrowserWindow({
      show: false,
      skipTaskbar: true,
      focusable: false,
      width: 320,
      height: 200,
      title: 'Nova screen recorder',
      webPreferences: {
        preload: PRELOAD,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        // Hidden on purpose: its chunk handling must never be throttled.
        backgroundThrottling: false,
      },
    });
    recorderWindows.add(page);
    win = page;
    page.webContents.on('render-process-gone', (_e, details) =>
      pageGone(page, `the recorder process ended (${details?.reason ?? 'unknown'})`));
    page.on('closed', () => {
      if (!stopped) pageGone(page, 'the recorder window closed');
    });
    Promise.resolve(page.loadFile(pagePath)).catch((err) =>
      pageGone(page, `the recorder page did not load: ${errLine(err)}`));
  }

  const fromPage = (event) => Boolean(win) && !win.isDestroyed() && event?.sender === win.webContents;
  const onReady = (event) => {
    if (!fromPage(event)) return;
    ready = true;
    pageError = null;
    void replan('start');
  };
  const onChunkMsg = (event, msg) => {
    if (fromPage(event)) onChunk(msg?.id, msg?.bytes);
  };
  const onEventMsg = (event, ev) => {
    if (fromPage(event)) onEvent(ev);
  };
  ipcMain.on(SCREEN_REC_READY_CHANNEL, onReady);
  ipcMain.on(SCREEN_REC_CHUNK_CHANNEL, onChunkMsg);
  ipcMain.on(SCREEN_REC_EVENT_CHANNEL, onEventMsg);

  async function checkDisk() {
    disk.checked = now();
    const { free, error } = await freeBytes(target.dir);
    disk = { free, error, checked: disk.checked };
  }

  function tick() {
    if (stopped) return;
    ensurePage();
    const t = now();
    for (const seg of [...segments.values()]) {
      if (seg.stopping) {
        if (t - seg.stopRequestedAt > P.SCREEN_RECORD_STOP_TIMEOUT_MS) void finalize(seg);
        continue;
      }
      const state = states.get(seg.key);
      if (!seg.startedAt) {
        if (t - seg.requestedAt > P.SCREEN_RECORD_START_TIMEOUT_MS) {
          onError({ id: seg.id, message: `the capture did not start within ${P.SCREEN_RECORD_START_TIMEOUT_MS / 1000} s` });
          send({ cmd: 'stop', id: seg.id });
        }
      } else if (state?.active === seg && t - seg.lastDataAt > P.SCREEN_RECORD_STALL_MS) {
        state.active = null;
        stopSegment(seg, 'stall');
        noteFailure(state, 'stall', `no video for ${P.SCREEN_RECORD_STALL_MS / 1000} s`);
      }
    }
    if ([...states.values()].some((s) => s.active && !s.pending && t >= s.rotateAt)) target = resolveTarget();
    if (ready && !suspended && (unmatched.length || planError) && t - lastPlanAt > REPLAN_UNMATCHED_MS) void replan('retry');
    ensureAll();
    if (t - disk.checked > P.SCREEN_RECORD_DISK_CHECK_MS) void checkDisk().then(publish);
    publish();
  }

  const onDisplay = () => scheduleReplan();
  const DISPLAY_EVENTS = ['display-added', 'display-removed', 'display-metrics-changed'];
  for (const name of DISPLAY_EVENTS) screen.on?.(name, onDisplay);
  const onSuspend = () => {
    suspended = true;
    for (const state of states.values()) {
      for (const seg of [state.active, state.pending]) if (seg) stopSegment(seg, 'suspend');
      Object.assign(state, { active: null, pending: null, since: null });
    }
    publish();
  };
  const onResume = () => {
    suspended = false;
    void replan('resume');
  };
  // The lock screen can take the capture away; back at the desk, no monitor waits out a backoff.
  const onUnlock = () => {
    for (const state of states.values()) state.retryAt = 0;
    ensureAll();
  };
  powerMonitor?.on?.('suspend', onSuspend);
  powerMonitor?.on?.('resume', onResume);
  powerMonitor?.on?.('unlock-screen', onUnlock);

  const interval = timers.setInterval(tick, P.SCREEN_RECORD_WATCH_MS);
  interval.unref?.();
  // New files on the quarter hour itself, not up to one watch interval late.
  let boundaryTimer = null;
  const armBoundary = () => {
    const t = now();
    boundaryTimer = timers.setTimeout(() => {
      tick();
      if (!stopped) armBoundary();
    }, P.nextBoundaryMs(t, segmentMs) - t + 5);
    boundaryTimer.unref?.();
  };
  armBoundary();
  ensurePage();
  void checkDisk().then(publish);

  function view() {
    const t = now();
    const displays = [...states.values()]
      .sort((a, b) => a.plan.display.index - b.plan.display.index)
      .map((s) => ({
        index: s.plan.display.index,
        count: s.plan.display.count,
        id: s.plan.display.id,
        label: s.plan.display.label,
        primary: s.plan.display.primary,
        scale_factor: s.plan.display.scale_factor,
        width: s.plan.width,
        height: s.plan.height,
        recording: Boolean(s.active) && !stopped,
        since: stopped ? null : sec(s.since),
        file: s.active?.file && !stopped ? path.basename(s.active.file.file) : null,
        bytes: s.active?.file && !stopped ? s.active.file.bytes : 0,
        last_data_ts: stopped ? null : sec(s.active?.lastDataAt ?? null),
        error: s.error,
        retry_at: !s.active && s.retryAt > t ? sec(s.retryAt) : null,
      }));
    const on = displays.filter((d) => d.recording).length;
    let state;
    if (stopped) state = 'stopped';
    else if (suspended) state = 'suspended';
    else if (displays.length && on === displays.length && !unmatched.length) state = 'recording';
    else if (on > 0) state = 'partial';
    else if (t - startedAt < SCREEN_RECORD_START_GRACE_MS && !pageError && !restarts) state = 'starting';
    else state = 'failed';
    const firstError = displays.find((d) => d.error)?.error ?? null;
    return {
      schema_version: P.SCREEN_RECORD_SCHEMA_VERSION,
      state,
      recording: state === 'recording',
      since: state === 'recording' ? Math.max(...displays.map((d) => d.since ?? 0)) || null : null,
      error: state === 'recording' ? null : (pageError ?? planError ?? firstError),
      dir: target.dir,
      dir_source: target.source,
      dir_note: target.note,
      dir_error: target.error,
      mime,
      fps: P.SCREEN_RECORD_FPS,
      segment_min: segmentMs / 60_000,
      displays,
      unmatched: unmatched.map((d) => ({ index: d.index, id: d.id, label: d.label })),
      disk: { free_bytes: disk.free, state: P.diskState(disk.free), error: disk.error, checked_ts: sec(disk.checked || null) },
      problems: problems.map((p) => ({ ...p })),
      restarts,
      generated_at: sec(t),
    };
  }

  return {
    view,
    isRecorderWindow: (w) => Boolean(w) && recorderWindows.has(w),
    /** Quitting: stop every capture and close every file; the last timeslice may not reach the disk. */
    stop(reason = 'quit') {
      if (stopped) return;
      for (const seg of [...segments.values()]) stopSegment(seg, reason);
      stopped = true;
      timers.clearInterval(interval);
      if (boundaryTimer) timers.clearTimeout(boundaryTimer);
      if (settleTimer) timers.clearTimeout(settleTimer);
      for (const name of DISPLAY_EVENTS) screen.removeListener?.(name, onDisplay);
      powerMonitor?.removeListener?.('suspend', onSuspend);
      powerMonitor?.removeListener?.('resume', onResume);
      powerMonitor?.removeListener?.('unlock-screen', onUnlock);
      ipcMain.removeListener(SCREEN_REC_READY_CHANNEL, onReady);
      ipcMain.removeListener(SCREEN_REC_CHUNK_CHANNEL, onChunkMsg);
      ipcMain.removeListener(SCREEN_REC_EVENT_CHANNEL, onEventMsg);
      finalizeNow();
      publish();
    },
  };
}
