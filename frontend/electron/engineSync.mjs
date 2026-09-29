/**
 * The operator's "Pull master and restart" for the backend's checkout (ADR 038 amendment,
 * 2026-09-29).
 *
 * The desk updates itself through the installer; the backend's code comes from git and loads only
 * when its process restarts, so the two drift apart (desk v1027 on backend v1025). When the
 * backend's checkout itself holds nothing newer, a restart alone cannot help: the desk's backend
 * notice offers this action, and it runs only when the operator presses it, after the desk listed
 * what is open. It pulls master into the owner's checkout -- fast-forward only, on master, with no
 * uncommitted changes, and never when master changes the backend's Python packages -- then
 * restarts the backend onto it. Nothing here runs on a timer. Every outcome goes to update.log and
 * to the update view's `engine` part (`{owner, attached_to_owner, running, last}`).
 */
import { execFile } from 'node:child_process';
import { isOlderTag } from './appTitle.mjs';
import { ownerRootFromEngine, readEngineOwner, sameRoot, writeEngineOwner } from './engineOwnership.mjs';
import { engineHome, getJson } from './engineRestart.mjs';
import { formatReleaseTag } from './releaseTag.mjs';

/** A pull that changes these would start a backend without its packages: install them first. */
export const ENGINE_SYNC_BLOCKING_FILES = ['backend/requirements.txt'];
const GIT_TIMEOUT_MS = 20_000;
const GIT_FETCH_TIMEOUT_MS = 120_000;
const GIT_MAX_BUFFER = 4 * 1024 * 1024;

function lastLine(output) {
  const lines = String(output ?? '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.length ? lines[lines.length - 1] : 'no output';
}

function message(err) {
  return err instanceof Error ? err.message : String(err ?? 'unknown error');
}

/** `git -C root ...` without a window or a credential prompt: `{code, stdout, stderr}`, never throws. */
export function runGit(root, args, { timeoutMs = GIT_TIMEOUT_MS, execFileFn = execFile, env = process.env } = {}) {
  return new Promise((resolve) => {
    execFileFn(
      'git',
      ['-C', root, ...args],
      { windowsHide: true, timeout: timeoutMs, maxBuffer: GIT_MAX_BUFFER, env: { ...env, GIT_TERMINAL_PROMPT: '0' } },
      (err, stdout, stderr) => {
        const code = err ? (typeof err.code === 'number' ? err.code : -1) : 0;
        resolve({ code, stdout: String(stdout ?? ''), stderr: String(stderr ?? '') || (err ? message(err) : '') });
      },
    );
  });
}

/** The checkout's revision on disk (`v1027`), or null when git cannot say. */
export async function checkoutRevision(root, git = runGit) {
  const out = await git(root, ['rev-list', '--count', 'HEAD']);
  return out.code === 0 ? formatReleaseTag(Number(out.stdout.trim())) || null : null;
}

/**
 * Pull master into `root`, fast-forward only: `{ok, pulled, from, to, reason}`, where `reason`
 * says why not in the operator's words. Never touches a checkout that is not a clean master.
 */
export async function pullMaster(root, git = runGit) {
  const fail = (reason, from = null) => ({ ok: false, pulled: false, from, to: from, reason });
  const branch = await git(root, ['rev-parse', '--abbrev-ref', 'HEAD']);
  if (branch.code !== 0) return fail(`git could not read the checkout: ${lastLine(branch.stderr)}`);
  const name = branch.stdout.trim();
  if (name !== 'master') return fail(`the checkout is on ${name}, not master`);
  const status = await git(root, ['status', '--porcelain', '--untracked-files=no']);
  if (status.code !== 0) return fail(`git could not read the checkout: ${lastLine(status.stderr)}`);
  const dirty = status.stdout.split(/\r?\n/).filter((l) => l.trim()).length;
  if (dirty) return fail(`the checkout has ${dirty} changed file${dirty === 1 ? '' : 's'} nobody committed`);
  const from = await checkoutRevision(root, git);
  const fetched = await git(root, ['fetch', '--quiet', 'origin', 'master'], { timeoutMs: GIT_FETCH_TIMEOUT_MS });
  if (fetched.code !== 0) return fail(`git fetch failed: ${lastLine(fetched.stderr)}`, from);
  const behind = await git(root, ['rev-list', '--count', 'HEAD..origin/master']);
  const count = Number(behind.stdout.trim());
  if (behind.code !== 0 || !Number.isInteger(count)) return fail(`git could not compare with master: ${lastLine(behind.stderr)}`, from);
  if (count === 0) return { ok: true, pulled: false, from, to: from, reason: null };
  const ancestor = await git(root, ['merge-base', '--is-ancestor', 'HEAD', 'origin/master']);
  if (ancestor.code !== 0) return fail('the checkout has commits master does not have', from);
  const blocking = await git(root, ['diff', '--name-only', 'HEAD', 'origin/master', '--', ...ENGINE_SYNC_BLOCKING_FILES]);
  if (blocking.code !== 0) return fail(`git could not list master's changes: ${lastLine(blocking.stderr)}`, from);
  const files = blocking.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (files.length) {
    return fail(`master changes ${files.join(', ')}: install the new packages first (docs/live-desk-sync.md)`, from);
  }
  const merged = await git(root, ['merge', '--ff-only', '--quiet', 'origin/master']);
  if (merged.code !== 0) return fail(`git merge failed: ${lastLine(merged.stderr)}`, from);
  return { ok: true, pulled: true, from, to: await checkoutRevision(root, git), reason: null };
}

/**
 * @param {{ apiBase: string, userData: string, reloadEngine: () => Promise<{from: string|null, to: string|null}>,
 *   publish: (view: object) => void, logger: { info: Function, warn: Function },
 *   git?: Function, fetchJson?: Function, now?: () => number, fsDeps?: object }} deps
 */
export function createEngineSync({
  apiBase,
  userData,
  reloadEngine,
  publish,
  logger,
  git = runGit,
  fetchJson = getJson,
  now = Date.now,
  fsDeps = {},
  readOwner = readEngineOwner,
  writeOwner = writeEngineOwner,
}) {
  let owner = readOwner(userData)?.repo_root ?? null;
  let attached = false;
  let running = null;
  let last = null;

  const view = () => ({ owner, attached_to_owner: attached, running, last });
  const emit = () => publish(view());

  function record(outcome, text) {
    last = { at: now(), outcome, text };
    (outcome === 'failed' ? logger.warn : logger.info)(`backend sync: ${text}`);
    emit();
  }

  /** Who answers :8000; a main checkout's engine becomes (or stays) the remembered owner. */
  async function look() {
    const home = await engineHome(apiBase, fetchJson);
    const root = ownerRootFromEngine(home, fsDeps);
    if (root && !sameRoot(root, owner) && writeOwner(userData, root)) {
      owner = root;
      logger.info(`backend owner: ${root}`);
    }
    attached = Boolean(home && !home.frozen && owner && sameRoot(home.root, owner));
    emit();
    return home;
  }

  async function step(kind, fn) {
    running = kind;
    emit();
    try {
      return await fn();
    } finally {
      running = null;
      emit();
    }
  }

  /** The operator pressed "Pull master and restart" (the desk listed what is open first). */
  async function syncNow() {
    if (running) return;
    const home = await look();
    if (!home) {
      record('failed', 'No backend answers on port 8000');
      return;
    }
    if (!attached) {
      record('failed', 'The backend is not running from your checkout, so there is nothing to pull');
      return;
    }
    const pulled = await step('pull', () => pullMaster(owner, git));
    if (!pulled.ok) {
      record('failed', `Not pulled: ${pulled.reason}`);
      return;
    }
    if (pulled.pulled) record('pulled', `Pulled master into ${owner}: ${pulled.from ?? '?'} -> ${pulled.to ?? '?'}`);
    const checkout = await checkoutRevision(owner, git);
    if (!isOlderTag(home.release_tag, checkout)) {
      record('current', `The backend already runs ${home.release_tag ?? "its checkout's code"}; master had nothing newer`);
      return;
    }
    try {
      const out = await step('restart', () => reloadEngine());
      record('restarted', `Restarted the backend: ${out.from ?? home.release_tag ?? '?'} -> ${out.to ?? '?'}`);
    } catch (err) {
      record('failed', `Pulled, but the restart failed: ${message(err)}`);
    }
  }

  return {
    view,
    look: () => look().catch((err) => {
      logger.warn(`backend owner check failed: ${message(err)}`);
      return null;
    }),
    syncNow: () => syncNow().catch((err) => {
      running = null;
      record('failed', `Pull and restart failed: ${message(err)}`);
    }),
  };
}

/** Publish the view as the update bridge's `engine` part and answer its `backend-sync` action. */
export function attachEngineSync({ bridge, ...deps }) {
  const sync = createEngineSync({ ...deps, publish: (view) => bridge.set('engine', view) });
  bridge.on('backend-sync', () => sync.syncNow());
  void sync.look();
  return sync;
}
