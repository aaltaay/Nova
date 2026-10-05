/**
 * The desk runs above background work (ADR 045): the Electron main process, its GPU process and
 * every desk window's renderer are kept at Above Normal, re-checked every PROCESS_PRIORITY_RECHECK_MS.
 *
 * 2026-10-05: explorer.exe -- and so everything the operator opened, Nova included -- ran BelowNormal
 * beside an ASUS game booster, and the backend read BelowNormal minutes after it had raised itself to
 * Normal. Builds, browsers and agents at Normal then took the CPU first. The backend keeps its own
 * processes and IB Gateway up (backend/process_priority/trading_path.py); this keeps the desk up.
 *
 * Only ever raises (`os.setPriority` to PRIORITY_ABOVE_NORMAL when a process reads lower); the hidden
 * screen-recorder and clip pages are not desk windows and keep what they have. Windows only. Electron
 * and `os` are passed in (main.mjs), so this module is testable without an Electron runtime.
 */

export const PROCESS_PRIORITY_RECHECK_MS = 2_000;
/** A demotion is logged once per process and this often after. */
const WARN_EVERY_MS = 600_000;

/** The pids to keep up: this main process, the GPU process(es), and each desk window's renderer. */
export function deskPids({ mainPid, metrics, windows, isDeskWindow }) {
  const pids = new Set([mainPid]);
  for (const m of metrics ?? []) {
    if (m && m.type === 'GPU' && m.pid) pids.add(m.pid);
  }
  for (const win of windows ?? []) {
    try {
      if (!win || win.isDestroyed() || !isDeskWindow(win)) continue;
      const pid = win.webContents.getOSProcessId();
      if (pid) pids.add(pid);
    } catch {
      /* a window closing mid-read has no process to raise */
    }
  }
  return pids;
}

/**
 * Raise each pid that reads below Above Normal. `os.getPriority` is a nice value: lower means higher
 * priority (Above Normal is -7). Returns `{ raised: [pid], failed: [{pid, error}] }`.
 */
export function raisePids(os, pids) {
  const target = os.constants.priority.PRIORITY_ABOVE_NORMAL;
  const raised = [];
  const failed = [];
  for (const pid of pids) {
    try {
      if (os.getPriority(pid) > target) {
        os.setPriority(pid, target);
        raised.push(pid);
      }
    } catch (error) {
      failed.push({ pid, error: String(error?.message ?? error) });
    }
  }
  return { raised, failed };
}

/** Start the keeper; returns its stop. A no-op off Windows. */
export function startProcessPriority({ app, BrowserWindow, isDeskWindow, os, platform = process.platform, log = console }) {
  if (platform !== 'win32') return () => {};
  const seen = new Set();          // pids raised once already: a later raise means something lowered them
  const warnedAt = new Map();
  const tick = () => {
    let pids;
    try {
      pids = deskPids({
        mainPid: process.pid,
        metrics: app.getAppMetrics(),
        windows: BrowserWindow.getAllWindows(),
        isDeskWindow,
      });
    } catch (error) {
      log.warn?.(`[priority] could not list the desk's processes: ${error}`);
      return;
    }
    const { raised, failed } = raisePids(os, pids);
    const now = Date.now();
    for (const pid of raised) {
      if (seen.has(pid) && now - (warnedAt.get(pid) ?? 0) >= WARN_EVERY_MS) {
        warnedAt.set(pid, now);
        log.warn?.(`[priority] desk process ${pid} was lowered by something on this PC; raised to Above Normal`);
      }
      seen.add(pid);
    }
    for (const { pid, error } of failed) {
      if (now - (warnedAt.get(pid) ?? 0) >= WARN_EVERY_MS) {
        warnedAt.set(pid, now);
        log.warn?.(`[priority] could not raise desk process ${pid}: ${error}`);
      }
    }
  };
  tick();
  const timer = setInterval(tick, PROCESS_PRIORITY_RECHECK_MS);
  return () => clearInterval(timer);
}
