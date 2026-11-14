/**
 * The desk keeps the phone page built and served (ADR 070 amendment 2026-11-14; operator: "It needs to get
 * reloaded as a part of the installation. Automatically").
 *
 * The phone loads a built copy of its page (`frontend/dist`) from a small file server on 127.0.0.1:4181, which
 * the private tunnel forwards to. Both lived outside the desk: a release pulled the checkout forward and the
 * phone kept the old page until someone ran `tools/phone_page.py update`, and the file server, started by hand,
 * was gone after a reboot. So, once a minute, the installed desk:
 * - asks the owner's checkout (ADR 038, the one the backend runs from) whether the page is its code
 *   (`phone_page.py check`) and, when not, rebuilds it there (`phone_page.py update`) below normal priority --
 *   never while the desk pulls or restarts the backend, and a failed build waits 30 minutes (or a new checkout);
 * - asks 4181 for the page and, when nothing answers, starts `tools/serve_phone_page.py` from that checkout,
 *   with no window, in a process of its own that outlives the desk.
 * Every outcome goes to update.log and to the update view's `phone_page` part. `NOVA_PHONE_PAGE=0` turns it off.
 */
import { execFile, spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

export const PHONE_PAGE_PORT = 4181;
export const PHONE_PAGE_TICK_MS = 60_000;
/** A build that failed is tried again after this, or at once when the checkout's revision moves. */
export const PHONE_PAGE_RETRY_MS = 30 * 60_000;
/** A server just started gets this long to answer before the desk starts another. */
export const PHONE_PAGE_START_GRACE_MS = 60_000;
const CHECK_TIMEOUT_MS = 60_000;
const BUILD_TIMEOUT_MS = 15 * 60_000;
const PROBE_TIMEOUT_MS = 3_000;
const OUTPUT_MAX = 4 * 1024 * 1024;

function message(err) {
  return err instanceof Error ? err.message : String(err ?? 'unknown error');
}

function lastLine(output) {
  const lines = String(output ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : 'no output';
}

/** The python.exe behind `py -3`, or null: the server is started with it directly, so no console comes up. */
export function resolvePython({ run = spawnSync } = {}) {
  try {
    const out = run('py', ['-3', '-c', 'import sys; print(sys.executable)'], { encoding: 'utf8', windowsHide: true, timeout: 20_000 });
    const exe = String(out?.stdout ?? '').trim();
    return out?.status === 0 && exe ? exe : null;
  } catch {
    return null; // maintainer: allow-swallow no Python is said by the caller as "cannot start"
  }
}

/** Run a Python tool in `root`, hidden: `{code, stdout, stderr}`, never throws. `low` runs it below normal priority. */
export function runTool(python, root, args, { timeoutMs, low = false, execFileFn = execFile, setPriority = os.setPriority } = {}) {
  return new Promise((resolve) => {
    const child = execFileFn(
      python,
      args,
      { cwd: root, windowsHide: true, timeout: timeoutMs, maxBuffer: OUTPUT_MAX },
      (err, stdout, stderr) => {
        const code = err ? (typeof err.code === 'number' ? err.code : -1) : 0;
        resolve({ code, stdout: String(stdout ?? ''), stderr: String(stderr ?? '') || (err ? message(err) : '') });
      },
    );
    if (low && child?.pid) {
      // npm and the build it starts inherit a below-normal class on Windows: the trading path keeps the PC.
      try {
        setPriority(child.pid, os.constants.priority.PRIORITY_BELOW_NORMAL);
      } catch {
        // maintainer: allow-swallow a build at normal priority still builds
      }
    }
  });
}

/** True when the page server answers 200 for the phone page; false on anything else. */
export function probePage({ port = PHONE_PAGE_PORT, timeoutMs = PROBE_TIMEOUT_MS, get = http.get } = {}) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      resolve(ok);
    };
    try {
      const req = get({ host: '127.0.0.1', port, path: '/phone.html', method: 'HEAD', timeout: timeoutMs }, (res) => {
        res.resume?.();
        finish(res.statusCode === 200);
      });
      req.on('timeout', () => {
        req.destroy();
        finish(false);
      });
      req.on('error', () => finish(false));
    } catch {
      finish(false); // maintainer: allow-swallow an unreachable server reads as not served
    }
  });
}

/** Start the page server from `root` with no window, in a process of its own that outlives the desk. */
export function startPageServer(python, root, { spawnFn = spawn } = {}) {
  const child = spawnFn(python, [path.join(root, 'tools', 'serve_phone_page.py')], {
    cwd: root,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  });
  child.on?.('error', (err) => console.error('[phone-page] server start failed', err));
  child.unref?.();
}

/**
 * @param {{ root: () => string | null, busy?: () => boolean, revision?: (root: string) => Promise<string | null>,
 *   publish: (view: object) => void, logger: { info: Function, warn: Function },
 *   python?: () => string | null, run?: typeof runTool, probe?: () => Promise<boolean>,
 *   start?: (python: string, root: string) => void, exists?: (p: string) => boolean, now?: () => number }} deps
 */
export function createPhonePageKeeper({
  root,
  busy = () => false,
  revision = async () => null,
  publish,
  logger,
  python = (() => {
    let cached;
    return () => (cached === undefined ? (cached = resolvePython()) : cached);
  })(),
  run = runTool,
  probe = () => probePage(),
  start = startPageServer,
  exists = fs.existsSync,
  now = Date.now,
}) {
  let view = null;
  let ticking = false;
  let failed = null; // {at, rev}: the last build that failed, and the checkout it failed on
  let startedAt = 0;

  const emit = (next) => {
    view = next;
    publish(view);
  };
  const keep = (patch) => emit({ root: null, build: null, served: null, last: null, ...view, ...patch });
  function record(outcome, text, patch = {}) {
    (outcome === 'failed' ? logger.warn : logger.info)(`phone page: ${text}`);
    keep({ ...patch, last: { at: now(), outcome, text } });
  }

  async function keepBuilt(checkout, exe) {
    const frontend = path.join(checkout, 'frontend');
    const tool = path.join(checkout, 'tools', 'phone_page.py');
    const check = await run(exe, checkout, [tool, 'check', '--frontend', frontend], { timeoutMs: CHECK_TIMEOUT_MS });
    if (check.code === 0) {
      failed = null;
      if (view?.build !== 'current') keep({ build: 'current' });
      return;
    }
    if (check.code !== 1) {
      record('failed', `Could not tell whether the phone page is current: ${lastLine(check.stderr || check.stdout)}`, { build: null });
      return;
    }
    const rev = await revision(checkout);
    if (failed && failed.rev === rev && now() - failed.at < PHONE_PAGE_RETRY_MS) return;
    keep({ build: 'building' });
    logger.info(`phone page: rebuilding from ${checkout}${rev ? ` at ${rev}` : ''}`);
    const out = await run(exe, checkout, [tool, 'update', '--frontend', frontend], { timeoutMs: BUILD_TIMEOUT_MS, low: true });
    if (out.code === 0) {
      failed = null;
      record('built', `Rebuilt the phone page${rev ? ` for ${rev}` : ''}: reload it on the phone`, { build: 'current' });
      return;
    }
    failed = { at: now(), rev };
    record('failed', `The phone page did not rebuild (${lastLine(out.stderr || out.stdout)}); the phone keeps the page it had`, { build: 'failed' });
  }

  async function keepServed(checkout, exe) {
    if (await probe()) {
      startedAt = 0;
      if (view?.served !== true) keep({ served: true });
      return;
    }
    if (startedAt && now() - startedAt < PHONE_PAGE_START_GRACE_MS) return;
    // A start a minute ago that still does not answer is a failure the desk says, not a quiet retry.
    const unanswered = startedAt !== 0;
    startedAt = now();
    try {
      start(exe, checkout);
      if (unanswered) {
        record('failed', `The phone page server did not answer a minute after it was started; started it again from ${checkout}`, { served: false });
      } else {
        record('started', `Started the phone page server on 127.0.0.1:${PHONE_PAGE_PORT} from ${checkout}`, { served: false });
      }
    } catch (err) {
      record('failed', `The phone page server could not be started: ${message(err)}`, { served: false });
    }
  }

  /** One look: rebuild a page that is behind, then make sure the server answers. Never throws, never overlaps. */
  async function tick() {
    if (ticking) return;
    ticking = true;
    try {
      const checkout = root();
      if (!checkout || !exists(path.join(checkout, 'tools', 'phone_page.py'))) {
        if (view?.root !== null || view === null) keep({ root: null, build: null, served: null });
        return;
      }
      if (view?.root !== checkout) keep({ root: checkout });
      const exe = python();
      if (!exe) {
        if (view?.last?.text !== NO_PYTHON) record('failed', NO_PYTHON, { served: false });
        return;
      }
      // A pull or restart under way changes the files the build reads: the next look builds.
      if (!busy()) await keepBuilt(checkout, exe);
      await keepServed(checkout, exe);
    } catch (err) {
      record('failed', `The phone page check failed: ${message(err)}`);
    } finally {
      ticking = false;
    }
  }

  return { tick, view: () => view };
}

const NO_PYTHON = 'Python (py -3) was not found, so the phone page cannot be built or served';

/** The off switch: `NOVA_PHONE_PAGE=0` leaves the page and its server to the operator. */
export function phonePageKeeperOn(env = process.env) {
  return String(env.NOVA_PHONE_PAGE ?? '').trim() !== '0';
}

/** Publish the keeper as the update bridge's `phone_page` part, and look now and once a minute. */
export function attachPhonePageKeeper({ bridge, env = process.env, ...deps }) {
  if (!phonePageKeeperOn(env)) {
    deps.logger.info('phone page: NOVA_PHONE_PAGE=0, the desk leaves the page and its server alone');
    return null;
  }
  const keeper = createPhonePageKeeper({ ...deps, publish: (view) => bridge.set('phone_page', view) });
  void keeper.tick();
  const timer = setInterval(() => void keeper.tick(), PHONE_PAGE_TICK_MS);
  timer.unref?.();
  return keeper;
}
