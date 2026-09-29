/**
 * Who runs the backend the installed desk talks to (ADR 038, amended 2026-09-29).
 *
 * The operator's backend is the checkout engine that the localhost watchdog, Run Nova.bat and
 * the morning script start: its data sits behind the checkout's backend\.cache (F:\Nova\cache),
 * and its .env holds the IBKR settings and the Live PIN hash. So the installed desk:
 *  - uses whatever Nova engine answers :8000 without asking -- it never stops it and never
 *    starts a second engine over it -- and remembers a checkout engine's checkout as the owner;
 *  - with nothing on :8000, starts the owner's engine from that checkout (same data, same code);
 *  - starts its bundled engine, whose data lives in the app's own folder (a different Paper
 *    account, bot session and history), only when it knows no owner, or when the operator picks
 *    it for one session after the owner's engine failed to start.
 * Pure decisions and the owner file live here; sidecar.mjs probes and starts engines, and
 * engineSync.mjs pulls the owner's checkout when the operator asks.
 *
 * userData/engine-owner.json: {schema_version: 1, repo_root, seen_at} -- written whenever the
 * desk finds a checkout engine on :8000; an unknown version, a missing file or a checkout that no
 * longer holds its start script reads as no owner. Delete the file to go back to the bundled engine.
 */
import fs from 'node:fs';
import path from 'node:path';

export const ENGINE_OWNER_FILE = 'engine-owner.json';
export const ENGINE_OWNER_SCHEMA_VERSION = 1;

const START_SCRIPT = ['scripts', 'Start-NovaApi.ps1'];

function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/**
 * The engine answering /api/health as `{frozen, root, release_tag, checkout_tag}`, or null when
 * the body does not say (a backend older than the `frozen` field; ask its checklist instead).
 */
export function engineHomeFromHealth(body) {
  if (!body || typeof body !== 'object' || typeof body.frozen !== 'boolean') return null;
  return {
    frozen: body.frozen,
    root: body.frozen ? null : text(body.repo_root),
    release_tag: text(body.release_tag),
    checkout_tag: text(body.checkout_tag),
  };
}

/** Same folder, whatever the case or trailing separator (Windows paths). */
export function sameRoot(a, b) {
  const norm = (p) => (text(p) ? path.win32.normalize(p).replace(/[\\/]+$/, '').toLowerCase() : null);
  const x = norm(a);
  return x !== null && x === norm(b);
}

/**
 * The checkout an engine runs from, when it may own the desk's backend: a main checkout (its
 * `.git` is a folder -- an agent's worktree has a `.git` file and no `.env`) with a `.env` and
 * the start script. Null for a packaged engine or anything else.
 */
export function ownerRootFromEngine(home, { exists = fs.existsSync, isDir = isDirectory } = {}) {
  const root = home && !home.frozen ? text(home.root) : null;
  if (!root) return null;
  const at = (...parts) => path.win32.join(root, ...parts);
  if (!isDir(at('.git')) || !exists(at('.env')) || !exists(at(...START_SCRIPT))) return null;
  return root;
}

function isDirectory(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false; // missing: not a checkout
  }
}

/** The remembered owner `{repo_root, seen_at}`, or null (no file, unreadable, unknown version). */
export function readEngineOwner(userData, { readFile = fs.readFileSync } = {}) {
  let raw;
  try {
    raw = readFile(path.join(userData, ENGINE_OWNER_FILE), 'utf8');
  } catch {
    return null; // no owner remembered yet
  }
  try {
    const row = JSON.parse(raw);
    if (row?.schema_version !== ENGINE_OWNER_SCHEMA_VERSION || !text(row.repo_root)) return null;
    return { repo_root: text(row.repo_root), seen_at: Number(row.seen_at) || null };
  } catch (err) {
    console.warn('[nova-api] engine-owner.json unreadable; no owner remembered', err);
    return null;
  }
}

/** Remember `root` as the owner (temp file, then rename). Never throws: the desk works without it. */
export function writeEngineOwner(userData, root, { now = Date.now, fsApi = fs } = {}) {
  const file = path.join(userData, ENGINE_OWNER_FILE);
  const body = JSON.stringify({ schema_version: ENGINE_OWNER_SCHEMA_VERSION, repo_root: root, seen_at: now() });
  try {
    fsApi.mkdirSync(userData, { recursive: true });
    fsApi.writeFileSync(`${file}.tmp`, body, 'utf8');
    fsApi.renameSync(`${file}.tmp`, file);
    return true;
  } catch (err) {
    console.warn('[nova-api] could not remember the backend owner', err);
    return false;
  }
}

/** The owner's checkout still holds what starting its engine needs. */
export function ownerUsable(owner, deps = {}) {
  return Boolean(owner) && ownerRootFromEngine({ frozen: false, root: owner.repo_root }, deps) !== null;
}

/**
 * With nothing answering :8000: start the owner's engine from its checkout when one is known and
 * still there, else this app's bundled engine.
 */
export function emptyPortPlan(owner, deps = {}) {
  return ownerUsable(owner, deps) ? 'start_owner' : 'start_bundled';
}

/** The owner's engine did not come up: say why, and what the bundled engine would mean. */
export function ownerStartFailedPrompt({ root, error, userData }) {
  return {
    type: 'warning',
    title: 'Your Nova backend did not start',
    message: `Nova could not start the backend from ${root}.`,
    detail:
      `${error}\n\nRetry once it can start (Run Nova.bat shows why it cannot). The bundled backend `
      + `keeps its data in ${path.join(userData, 'cache')}: a different Paper account, bot session and `
      + 'history than your usual backend.',
    buttons: ['Retry', 'Use the bundled backend this session', 'Exit Nova'],
    defaultId: 0,
    cancelId: 2,
    noLink: true,
  };
}
