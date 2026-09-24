/**
 * "Reload backend" for an engine this app did not start (operator report 2026-09-24: the
 * button said "Backend reloaded" while v991 kept answering).
 *
 * The installed app looked for scripts/Stop-NovaPorts.ps1 beside itself, found none, stopped
 * nothing and re-attached to the engine it meant to replace. Now the engine names its own
 * checkout (/api/diagnostics `process.repo_root`), that checkout's stop script stops it -- the
 * script checks the listener is Nova's before it kills -- and a reload counts only when a
 * different process answers /api/health (a new `instance_id`). The localhost watchdog
 * (scripts/Watch-NovaLocalhost.ps1) starts the next engine; with no watchdog running, the
 * checkout's own scripts/Start-NovaApi.ps1 does, as Run Nova.bat would -- never this app's
 * packaged engine, which keeps its data in another folder. The engine's instance lock makes a
 * start beside the watchdog's harmless: the second one exits.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { windowsPowerShell } from './updateSplash.mjs';

export const ENGINE_STOP_SCRIPT = ['scripts', 'Stop-NovaPorts.ps1'];
export const ENGINE_START_SCRIPT = ['scripts', 'Start-NovaApi.ps1'];
/** The watchdog looks every 20 s, and a started engine can take most of a minute to answer. */
export const ENGINE_NEW_TIMEOUT_MS = 120_000;
const HEALTH_TIMEOUT_MS = 3_000;
/** The checklist probes the Gateway ports on a worker thread; a dark port costs seconds. */
const DIAGNOSTICS_TIMEOUT_MS = 20_000;
const STOP_TIMEOUT_MS = 30_000;
const WATCHDOG_QUERY_TIMEOUT_MS = 15_000;
const POLL_MS = 1_000;
const WATCHDOG_QUERY =
  "@(Get-CimInstance Win32_Process -Filter \"Name='powershell.exe' OR Name='pwsh.exe'\" | " +
  "Where-Object { $_.CommandLine -match 'Watch-NovaLocalhost' }).Count";

/** GET a JSON body; null when nothing answers, the status is not 200 or the body is not JSON. */
export function getJson(url, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const req = http.get(url, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('error', () => done(null));
      res.on('end', () => {
        if (res.statusCode !== 200) {
          done(null);
          return;
        }
        try {
          done(JSON.parse(Buffer.concat(chunks).toString('utf8')));
        } catch {
          done(null); // not JSON: not a Nova engine answering
        }
      });
    });
    req.on('error', () => done(null));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      done(null);
    });
  });
}

function text(value) {
  return typeof value === 'string' && value ? value : null;
}

/**
 * Who answers /api/health now -- `{instance_id, pid, release_tag}`, each null when the engine
 * does not say -- or null when no Nova engine answers.
 */
export async function engineIdentity(apiBase, fetchJson = getJson) {
  const body = await fetchJson(`${apiBase}/api/health`, HEALTH_TIMEOUT_MS);
  if (!body || typeof body.status !== 'string') return null;
  return {
    instance_id: text(body.instance_id),
    pid: Number.isInteger(body.pid) ? body.pid : null,
    release_tag: text(body.release_tag),
  };
}

/** The engine's own checkout and revision, from its checklist; null when it does not say. */
export async function engineCheckout(apiBase, fetchJson = getJson) {
  const proc = (await fetchJson(`${apiBase}/api/diagnostics`, DIAGNOSTICS_TIMEOUT_MS))?.process;
  if (!proc || typeof proc !== 'object') return null;
  // A packaged engine's repo_root is its unpack folder, which holds no scripts.
  return { root: proc.frozen === true ? null : text(proc.repo_root), release_tag: text(proc.release_tag) };
}

/** A different process answers: a new instance id, else a new pid, else the old one was seen gone. */
export function isNewEngine(before, after) {
  if (!after) return false;
  if (before?.instance_id && after.instance_id) return before.instance_id !== after.instance_id;
  if (before?.pid && after.pid) return before.pid !== after.pid;
  return true;
}

/** The first checkout root that holds the stop script, with its start script (null when missing). */
export function engineScripts(roots, exists = fs.existsSync) {
  for (const root of roots) {
    if (!root) continue;
    const stop = path.win32.join(root, ...ENGINE_STOP_SCRIPT);
    if (!exists(stop)) continue;
    const start = path.win32.join(root, ...ENGINE_START_SCRIPT);
    return { root, stop, start: exists(start) ? start : null, backendDir: path.win32.join(root, 'backend') };
  }
  return null;
}

/**
 * cmd.exe's whole command line (passed verbatim): start the checkout's engine the way Run
 * Nova.bat does, in its own hidden console in the backend folder, so it outlives this app.
 * Null when a path holds a character cmd would rewrite (`"`, `%`) or a line break.
 */
export function engineStartCommandLine(powershell, backendDir, startScript) {
  const parts = [powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', startScript];
  if ([...parts, backendDir].some((part) => /["%\r\n]/.test(part))) return null;
  const quote = (part) => (/[\s&|<>^()]/.test(part) ? `"${part}"` : part);
  return `/d /s /c "start "Nova API" /min /D ${quote(backendDir)} ${parts.map(quote).join(' ')}"`;
}

/** The engine's environment: this app's, less Electron's own switches. */
export function checkoutEngineEnv(env) {
  return Object.fromEntries(Object.entries(env).filter(([key]) => !key.startsWith('ELECTRON_')));
}

function cmdExe(env) {
  return path.win32.join(env.SystemRoot || env.windir || 'C:\\Windows', 'System32', 'cmd.exe');
}

/** True when the localhost watchdog runs (it starts the next engine); false when unknown. */
export function watchdogRunning({ run = spawnSync, env = process.env } = {}) {
  try {
    const encoded = Buffer.from(WATCHDOG_QUERY, 'utf16le').toString('base64');
    const result = run(windowsPowerShell(env), ['-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], {
      encoding: 'utf8',
      windowsHide: true,
      timeout: WATCHDOG_QUERY_TIMEOUT_MS,
    });
    return Number(String(result?.stdout ?? '').trim()) > 0;
  } catch (err) {
    console.warn('[nova-api] could not tell whether the localhost watchdog runs', err);
    return false;
  }
}

function lastLine(output) {
  const lines = String(output ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : '';
}

function label(tag) {
  return tag ? `backend ${tag}` : 'the backend';
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Poll /api/health until a different engine answers; null at the deadline. */
export async function waitForNewEngine(apiBase, before, { fetchJson = getJson, sleep = delay, now = Date.now, timeoutMs }) {
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const id = await engineIdentity(apiBase, fetchJson);
    if (isNewEngine(before, id)) return id;
    await sleep(POLL_MS);
  }
  return null;
}

/**
 * Stop an engine this app did not start and prove a different one answers.
 * @param {{instance_id: string|null, pid: number|null, release_tag: string|null}} before
 * @returns {Promise<{from: string|null, to: string|null}>} the revisions before and after
 * @throws {Error} "Not restarted: ..." / "Stopped ...: ..." saying what happened
 */
export async function restartCheckoutEngine(before, deps) {
  const {
    apiBase,
    port,
    ownRoot = null,
    waitForPortFree,
    platform = process.platform,
    fetchJson = getJson,
    run = spawnSync,
    spawnFn = spawn,
    exists = fs.existsSync,
    env = process.env,
    sleep = delay,
    now = Date.now,
    timeoutMs = ENGINE_NEW_TIMEOUT_MS,
  } = deps;
  if (platform !== 'win32') {
    throw new Error(`Not restarted: ${label(before.release_tag)} was started outside Nova; restart it where it runs`);
  }
  const checkout = await engineCheckout(apiBase, fetchJson);
  const from = before.release_tag ?? checkout?.release_tag ?? null;
  const scripts = engineScripts([checkout?.root, ownRoot], exists);
  if (!scripts) {
    throw new Error(`Not restarted: ${label(from)} was started outside Nova, and its stop script was not found`);
  }
  const watchdog = watchdogRunning({ run, env });
  console.log(`[nova-api] reload: stopping ${label(from)} from ${scripts.root} (watchdog ${watchdog ? 'running' : 'not running'})`);
  const stopped = run(windowsPowerShell(env), ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', scripts.stop, '-Ports', String(port)], {
    encoding: 'utf8',
    windowsHide: true,
    timeout: STOP_TIMEOUT_MS,
  });
  if (!(await waitForPortFree())) {
    const said = lastLine(stopped?.stdout);
    throw new Error(`Not restarted: ${label(from)} is still running${said ? ` -- ${said}` : ''}`);
  }
  if (!watchdog) {
    if (!scripts.start) throw new Error(`Stopped ${label(from)}, but Start-NovaApi.ps1 is missing -- run Run Nova.bat`);
    const commandLine = engineStartCommandLine(windowsPowerShell(env), scripts.backendDir, scripts.start);
    if (!commandLine) throw new Error(`Stopped ${label(from)}, but its folder path cannot be started from here -- run Run Nova.bat`);
    const child = spawnFn(cmdExe(env), [commandLine], {
      cwd: scripts.backendDir,
      detached: true,
      env: checkoutEngineEnv(env),
      stdio: 'ignore',
      windowsHide: true,
      windowsVerbatimArguments: true,
    });
    child.on?.('error', (err) => console.error('[nova-api] reload: engine start failed', err));
    child.unref?.();
  }
  const after = await waitForNewEngine(apiBase, before, { fetchJson, sleep, now, timeoutMs });
  if (!after) {
    throw new Error(`Stopped ${label(from)}; no backend answered within ${Math.round(timeoutMs / 1000)} s -- run Run Nova.bat`);
  }
  console.log(`[nova-api] reload: ${label(after.release_tag)} answers (was ${from ?? 'unknown'})`);
  return { from, to: after.release_tag };
}
