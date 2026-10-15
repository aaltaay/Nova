/**
 * The backend follows the desk, release for release (ADR 038 amendment 2026-09-29; one version,
 * operator ask 2026-09-30: "i need them to be treated as ONE").
 *
 * The desk updates itself through the installer; the backend's code comes from git and loads only
 * when its process restarts, so the two drifted apart (desk v1027 on backend v1025) -- and a pull
 * of master's newest commit put the backend ahead of the desk instead (desk v1050 on backend v1051,
 * whose installer was still being built). So the backend's checkout is brought to exactly the
 * release the desk runs -- its `vNNN` tag, fast-forward only, on a clean master, never when the
 * backend's Python packages change -- and never past it:
 * - at Restart to update (`prepareForDesk`): the checkout comes to the release being installed,
 *   after the desk listed what a restart would interrupt; once the "Updating Nova" window is up the
 *   backend restarts onto it (`handOffForInstall`), so it comes up while the installer runs, not
 *   after the new desk opens (operator report 2026-10-13: "Why doesn't the backend restart during
 *   installation?"). The new desk restarts it only if that did not happen (`followIfAsked`,
 *   engineFollow.mjs) -- one update for both;
 * - by itself (`follow`, every ENGINE_FOLLOW_TICK_MS), whenever the owner's backend runs a release
 *   older than this desk (operator ask 2026-10-13: "it should already know we need to restart the
 *   backend and restart it without us having to click on it"): the same pull and restart, once
 *   nothing open holds it (engineFollow.autoRestartHolds -- never a recording), once per pair of
 *   releases; what holds it is in `auto`, and a pull or restart that fails is left to the operator;
 * - on the backend notice's "Update backend to vNNN" (`syncNow`), when it was left to the operator.
 * It only ever brings the backend to the release this desk already runs, never master's newest
 * commit (an unattended pull of master is #616, parked). Every outcome goes to update.log and to the
 * update view's `engine` part (`{owner, attached_to_owner, running, last, auto}`).
 *
 * maintainer: one-concern every pull and restart of the backend shares one lock here, so none runs beside another
 */
import { execFile } from 'node:child_process';
import { isOlderTag } from './appTitle.mjs';
import {
  autoRestartHolds,
  cannotFollowPrompt,
  openNowPrompt,
  restartCheckLines,
  takeEngineFollow,
  writeEngineFollow,
} from './engineFollow.mjs';
import { ownerRootFromEngine, readEngineOwner, sameRoot, writeEngineOwner } from './engineOwnership.mjs';
import { engineHome, getJson } from './engineRestart.mjs';
import { formatReleaseTag } from './releaseTag.mjs';

/** A pull that changes these would start a backend without its packages: install them first. */
export const ENGINE_SYNC_BLOCKING_FILES = ['backend/requirements.txt'];
export const RESTART_CHECK_PATH = '/api/diagnostics/restart-check';
const RESTART_CHECK_TIMEOUT_MS = 5_000;
const GIT_TIMEOUT_MS = 20_000;
const GIT_FETCH_TIMEOUT_MS = 120_000;
const GIT_MAX_BUFFER = 4 * 1024 * 1024;
const TAG_RE = /^v\d+$/;
/** How often the desk looks whether its backend runs an older release, and whether what held it cleared. */
export const ENGINE_FOLLOW_TICK_MS = 15_000;

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
 * Bring `root` to release `tag` (a `vNNN` on master), fast-forward only: `{ok, pulled, from, to,
 * reason}`, where `reason` says why not in the operator's words. A checkout already at the release
 * is left alone; one past it too (`to` names where it is) -- master is never moved back. Never
 * touches a checkout that is not a clean master.
 */
export async function syncToRelease(root, tag, git = runGit) {
  const fail = (reason, from = null) => ({ ok: false, pulled: false, from, to: from, reason });
  if (!TAG_RE.test(String(tag ?? ''))) return fail('the desk does not know its own version');
  const branch = await git(root, ['rev-parse', '--abbrev-ref', 'HEAD']);
  if (branch.code !== 0) return fail(`git could not read the checkout: ${lastLine(branch.stderr)}`);
  const name = branch.stdout.trim();
  if (name !== 'master') return fail(`the checkout is on ${name}, not master`);
  const status = await git(root, ['status', '--porcelain', '--untracked-files=no']);
  if (status.code !== 0) return fail(`git could not read the checkout: ${lastLine(status.stderr)}`);
  const dirty = status.stdout.split(/\r?\n/).filter((l) => l.trim()).length;
  if (dirty) return fail(`the checkout has ${dirty} changed file${dirty === 1 ? '' : 's'} nobody committed`);
  const from = await checkoutRevision(root, git);
  const fetched = await git(root, ['fetch', '--quiet', 'origin', 'master', `+refs/tags/${tag}:refs/tags/${tag}`], {
    timeoutMs: GIT_FETCH_TIMEOUT_MS,
  });
  if (fetched.code !== 0) return fail(`git fetch failed: ${lastLine(fetched.stderr)}`, from);
  const target = await git(root, ['rev-parse', '--verify', '--quiet', `${tag}^{commit}`]);
  const sha = target.stdout.trim();
  if (target.code !== 0 || !sha) return fail(`GitHub has no ${tag} tag`, from);
  const onMaster = await git(root, ['merge-base', '--is-ancestor', sha, 'origin/master']);
  if (onMaster.code !== 0) return fail(`${tag} is not a commit on master`, from);
  const reached = await git(root, ['merge-base', '--is-ancestor', sha, 'HEAD']);
  if (reached.code === 0) return { ok: true, pulled: false, from, to: from, reason: null };
  const behind = await git(root, ['merge-base', '--is-ancestor', 'HEAD', sha]);
  if (behind.code !== 0) return fail('the checkout has commits master does not have', from);
  const blocking = await git(root, ['diff', '--name-only', 'HEAD', sha, '--', ...ENGINE_SYNC_BLOCKING_FILES]);
  if (blocking.code !== 0) return fail(`git could not list ${tag}'s changes: ${lastLine(blocking.stderr)}`, from);
  const files = blocking.stdout.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (files.length) {
    return fail(`${tag} changes ${files.join(', ')}: install the new packages first (docs/live-desk-sync.md)`, from);
  }
  const merged = await git(root, ['merge', '--ff-only', '--quiet', sha]);
  if (merged.code !== 0) return fail(`git merge failed: ${lastLine(merged.stderr)}`, from);
  return { ok: true, pulled: true, from, to: await checkoutRevision(root, git), reason: null };
}

/**
 * @param {{ apiBase: string, userData: string, deskTag: () => string,
 *   reloadEngine: () => Promise<{from: string|null, to: string|null}>,
 *   restartForInstall?: (reason: string) => Promise<{from: string|null, to: null}>,
 *   publish: (view: object) => void, logger: { info: Function, warn: Function },
 *   git?: Function, fetchJson?: Function, now?: () => number, fsDeps?: object }} deps
 */
export function createEngineSync({
  apiBase,
  userData,
  deskTag,
  reloadEngine,
  restartForInstall = null,
  publish,
  logger,
  git = runGit,
  fetchJson = getJson,
  now = Date.now,
  fsDeps = {},
  readOwner = readEngineOwner,
  writeOwner = writeEngineOwner,
  writeFollow = writeEngineFollow,
  takeFollow = takeEngineFollow,
}) {
  let owner = readOwner(userData)?.repo_root ?? null;
  let attached = false;
  let running = null;
  let last = null;
  // The restart by itself: what holds it, or why it is the operator's (`{state, holds, reason}`).
  let auto = null;
  let following = false;
  // `backend|desk` pairs already brought along once by itself: never a second time, so a restart that
  // comes back on the same code cannot loop.
  const tried = new Set();
  // The release Restart to update agreed to restart the backend onto (prepareForDesk), until the
  // install hands it off (handOffForInstall): `{tag}` or null.
  let handoff = null;
  // One checkout change at a time: the button, Restart to update's pull and the restart by itself
  // never pull or restart side by side (review on PR #909). `locked` while one runs.
  let lock = Promise.resolve();
  let locked = false;

  function exclusive(fn) {
    const run = lock.then(async () => {
      locked = true;
      try {
        return await fn();
      } finally {
        locked = false;
      }
    });
    lock = run.catch(() => undefined);
    return run;
  }

  const view = () => ({ owner, attached_to_owner: attached, running, last, auto });
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

  /**
   * Bring the backend to the desk's release: its checkout, then a restart onto it when it runs other
   * code. Waits for a pull or restart already under way, then looks again.
   */
  function syncNow() {
    return exclusive(syncNowUnlocked);
  }

  async function syncNowUnlocked() {
    if (running) return;
    const tag = deskTag();
    const home = await look();
    if (!home) {
      record('failed', 'No backend answers on port 8000');
      return;
    }
    if (!attached) {
      record('failed', 'The backend is not running from your checkout, so Nova cannot update it');
      return;
    }
    const pulled = await step('pull', () => syncToRelease(owner, tag, git));
    if (!pulled.ok) {
      record('failed', `Not updated: ${pulled.reason}`);
      return;
    }
    if (pulled.pulled) record('pulled', `Brought ${owner} to ${pulled.to ?? tag} (was ${pulled.from ?? '?'})`);
    const checkout = await checkoutRevision(owner, git);
    if (checkout && home.release_tag === checkout) {
      record('current', `The backend already runs ${checkout}`);
      return;
    }
    await restartOnto(checkout ?? tag, home);
  }

  /** Restart the backend onto what its checkout holds (`at`), and say how it went. */
  async function restartOnto(at, home) {
    try {
      const out = await step('restart', () => reloadEngine(`the desk updated the backend to ${at}`));
      record('restarted', `Restarted the backend: ${out.from ?? home.release_tag ?? '?'} -> ${out.to ?? '?'}`);
    } catch (err) {
      record('failed', `The checkout is at ${at}, but the restart failed: ${message(err)}`);
    }
  }

  /**
   * Restart to update, before the installer runs: list what a backend restart would interrupt,
   * bring the backend's checkout to `tag`, and leave the new desk the promise to restart it.
   * False when the operator chose to wait; true to install. `automatic` (the install Nova makes by
   * itself, autoInstall.mjs): no dialog -- what is open is read as the backend's own automatic restart
   * reads it (a recording passes), and anything it would ask about means wait.
   * @param {string} tag the release being installed
   * @param {{ box: (options: object) => Promise<{response: number}>, automatic?: boolean }} ui
   */
  async function prepareForDesk(tag, { box, automatic = false }) {
    handoff = null;
    const home = await look();
    // A bundled engine is replaced by the installer itself; another checkout's engine is not ours.
    if (home && !attached) return true;
    if (!owner) return true;
    if (automatic) {
      // A backend that does not answer holds it too (autoRestartHolds): never read as nothing open.
      const holds = await autoHolds();
      if (holds.length) {
        logger.info(`automatic update to ${tag} waits: ${holds.join('; ')}`);
        return false;
      }
    } else if (home) {
      const check = restartCheckLines(await fetchJson(`${apiBase}${RESTART_CHECK_PATH}`, RESTART_CHECK_TIMEOUT_MS));
      if (check.safe !== true && (await box(openNowPrompt(tag, check.lines)))?.response !== 0) {
        logger.info(`update to ${tag} put off: something is open on the backend`);
        return false;
      }
    }
    const pulled = await exclusive(() => step('pull', () => syncToRelease(owner, tag, git)));
    if (!pulled.ok) {
      record('failed', `Not updated to ${tag}: ${pulled.reason}`);
      if (automatic) return false;
      return (await box(cannotFollowPrompt(tag, pulled.reason)))?.response === 1;
    }
    if (pulled.pulled) record('pulled', `Brought ${owner} to ${pulled.to ?? tag} (was ${pulled.from ?? '?'})`);
    if (automatic) {
      // The pull can take two minutes: a trade placed meanwhile holds the install until the next look.
      const late = await autoHolds();
      if (late.length) {
        logger.info(`automatic update to ${tag} waits: ${late.join('; ')}`);
        return false;
      }
    }
    if (home && home.release_tag !== tag) {
      writeFollow(userData, { tag, repoRoot: owner, now: now() });
      handoff = { tag };
    }
    return true;
  }

  /**
   * Restart to update, once the "Updating Nova" window is up and right before the installer runs:
   * restart the backend onto the release prepareForDesk brought its checkout to, so it comes up
   * while the installer runs. Only onto that exact release, read again now. The promise stays: if
   * the restart did not happen here, the new desk makes it (followIfAsked), as before.
   */
  async function handOffForInstall() {
    const plan = handoff;
    handoff = null;
    if (!plan || !restartForInstall) return;
    await exclusive(async () => {
      const checkout = await checkoutRevision(owner, git);
      if (checkout !== plan.tag) {
        record('failed', `Left to the new desk: the checkout holds ${checkout ?? 'a revision git cannot name'}, not ${plan.tag}`);
        return;
      }
      try {
        const out = await step('restart', () => restartForInstall(`the desk is installing ${plan.tag}`));
        record('restarted', `Restarting the backend onto ${plan.tag} while the desk installs (was ${out?.from ?? '?'})`);
      } catch (err) {
        record('failed', `Left to the new desk: ${message(err)}`);
      }
    });
  }

  /** The new desk's launch: keep the old desk's promise to restart the backend onto this release. */
  async function followIfAsked() {
    const promise = takeFollow(userData, { now: now() });
    const tag = deskTag();
    if (!promise || promise.tag !== tag) return;
    const home = await look();
    if (!home || !attached || home.release_tag === tag) return;
    tried.add(`${home.release_tag}|${tag}`);
    logger.info(`updating the backend to ${tag}, as asked at Restart to update`);
    await syncNow();
  }

  function setAuto(next) {
    if (JSON.stringify(next) === JSON.stringify(auto)) return;
    auto = next;
    emit();
  }

  /** What holds the backend's automatic restart now (engineFollow.autoRestartHolds): [] when nothing does. */
  async function autoHolds() {
    return autoRestartHolds(await fetchJson(`${apiBase}${RESTART_CHECK_PATH}`, RESTART_CHECK_TIMEOUT_MS));
  }

  /**
   * The owner's backend runs a release older than this desk: bring it to the desk's release without
   * asking, as soon as nothing open holds it. Nothing to do for a backend at (or past) the desk's
   * release, a backend from another checkout, or one Nova already brought along for this pair. What
   * is open is read again after the pull (a fetch can take two minutes), right before the restart,
   * and it restarts only onto the desk's exact release: a checkout already past it (a pull of
   * master) would put the backend ahead of the desk, so that is left to the operator.
   */
  async function follow() {
    // A pull or restart under way (the operator's, or an earlier look): the next tick looks again.
    if (running || following || locked) return;
    following = true;
    try {
      await exclusive(followUnlocked);
    } finally {
      following = false;
    }
  }

  /** The checkout must hold the desk's exact release when the restart starts; else it is the operator's. */
  const pastDesk = (checkout, tag) => `Not restarted by itself: the checkout holds ${checkout ?? 'a revision git cannot name'}, `
    + `not ${tag}, and a restart loads the checkout`;

  async function followUnlocked() {
    const tag = deskTag();
    const home = await look();
    if (!home || !attached || !isOlderTag(home.release_tag, tag)) {
      setAuto(null);
      return;
    }
    const key = `${home.release_tag}|${tag}`;
    if (tried.has(key)) {
      // Brought along once and still behind: the button and its reason are the operator's.
      if (auto?.state !== 'left') setAuto({ state: 'left', holds: [], reason: last?.outcome === 'failed' ? last.text : '' });
      return;
    }
    const holds = await autoHolds();
    if (holds.length) {
      if (JSON.stringify(holds) !== JSON.stringify(auto?.holds)) {
        logger.info(`backend sync: ${home.release_tag} -> ${tag} waits: ${holds.join('; ')}`);
      }
      setAuto({ state: 'waiting', holds, reason: '' });
      return;
    }
    setAuto(null);
    logger.info(`backend sync: updating the backend to ${tag} by itself (it ran ${home.release_tag}, nothing open)`);
    const left = (reason) => {
      tried.add(key);
      record('failed', reason);
      setAuto({ state: 'left', holds: [], reason });
    };
    const pulled = await step('pull', () => syncToRelease(owner, tag, git));
    if (!pulled.ok) {
      left(`Not updated: ${pulled.reason}`);
      return;
    }
    if (pulled.pulled) record('pulled', `Brought ${owner} to ${pulled.to ?? tag} (was ${pulled.from ?? '?'})`);
    const checkout = await checkoutRevision(owner, git);
    if (checkout !== tag) {
      left(pastDesk(checkout, tag));
      return;
    }
    // The pull took a while: a trade placed meanwhile holds it, and it goes once that clears.
    const late = await autoHolds();
    if (late.length) {
      logger.info(`backend sync: ${home.release_tag} -> ${tag} waits: ${late.join('; ')}`);
      setAuto({ state: 'waiting', holds: late, reason: '' });
      return;
    }
    // That check can take seconds, and a pull from elsewhere (an IDE, a terminal) changes what loads.
    const atRestart = await checkoutRevision(owner, git);
    if (atRestart !== tag) {
      left(pastDesk(atRestart, tag));
      return;
    }
    tried.add(key);
    await restartOnto(tag, home);
    const after = await look();
    if (after && attached && isOlderTag(after.release_tag, tag)) {
      setAuto({ state: 'left', holds: [], reason: last?.outcome === 'failed' ? last.text : '' });
    }
  }

  const guard = (label, fn) => (...args) => fn(...args).catch((err) => {
    running = null;
    record('failed', `${label} failed: ${message(err)}`);
    return undefined;
  });

  return {
    view,
    look: () => look().catch((err) => {
      logger.warn(`backend owner check failed: ${message(err)}`);
      return null;
    }),
    syncNow: guard('Updating the backend', syncNow),
    // A failure here must not stop the desk's own update: the operator is told, then asked.
    // Nobody is asked about an automatic install: it waits for the operator's click.
    prepareForDesk: async (tag, ui) => {
      try {
        return await prepareForDesk(tag, ui);
      } catch (err) {
        running = null;
        record('failed', `Could not prepare the backend for ${tag}: ${message(err)}`);
        if (ui?.automatic) return false;
        return (await ui.box(cannotFollowPrompt(tag, message(err))))?.response === 1;
      }
    },
    // What holds an automatic update or backend restart now ([] when nothing does); never throws.
    autoHolds: () => autoHolds().catch((err) => [`Could not read what is open: ${message(err)}`]),
    // Never holds up the install: a failure here is the new desk's to retry.
    handOffForInstall: guard('Restarting the backend for the install', handOffForInstall),
    followIfAsked: guard('Updating the backend', followIfAsked),
    follow: guard('Updating the backend by itself', follow),
  };
}

/** Publish the view as the update bridge's `engine` part and answer its `backend-sync` action. */
export function attachEngineSync({ bridge, ...deps }) {
  const sync = createEngineSync({ ...deps, publish: (view) => bridge.set('engine', view) });
  bridge.on('backend-sync', () => sync.syncNow());
  void sync.look()
    .then(() => sync.followIfAsked())
    .then(() => sync.follow());
  // Whenever the backend falls behind this desk later (or what held it clears), it follows by itself.
  const timer = setInterval(() => void sync.follow(), ENGINE_FOLLOW_TICK_MS);
  timer.unref?.();
  return sync;
}
