/**
 * The desk and its backend update as one (operator ask 2026-09-30: "i need them to be treated as
 * ONE"). Owns the promise the old desk leaves for the new one, and the words of the two questions
 * Restart to update can ask.
 *
 * At Restart to update the old desk brings the backend's checkout to the release it installs
 * (engineSync.mjs) and writes `engine-follow.json` = `{schema_version: 1, tag, repo_root, asked_at}`
 * in userData. The new desk reads it once, deletes it, and -- when it is that release and the
 * backend still runs other code -- restarts the backend onto it without asking again: the operator
 * already said yes, after the desk listed what a restart would interrupt. An unknown version, an
 * unreadable file or one older than a day reads as no promise.
 */
import fs from 'node:fs';
import path from 'node:path';

export const ENGINE_FOLLOW_FILE = 'engine-follow.json';
export const ENGINE_FOLLOW_SCHEMA_VERSION = 1;
/** An install that took longer than this was not the one the promise was made for. */
export const ENGINE_FOLLOW_MAX_AGE_MS = 24 * 60 * 60 * 1000;

const TAG_RE = /^v\d+$/;

function followPath(userData) {
  return path.join(userData, ENGINE_FOLLOW_FILE);
}

/** Leave the new desk its promise; false when the file could not be written. */
export function writeEngineFollow(userData, { tag, repoRoot, now = Date.now() }, fsApi = fs) {
  if (!userData || !TAG_RE.test(String(tag ?? ''))) return false;
  const body = { schema_version: ENGINE_FOLLOW_SCHEMA_VERSION, tag, repo_root: repoRoot ?? null, asked_at: now };
  try {
    fsApi.writeFileSync(followPath(userData), `${JSON.stringify(body, null, 2)}\n`, 'utf8');
    return true;
  } catch (err) {
    console.warn('[nova-update] could not write the backend promise', err);
    return false;
  }
}

/** Read the promise and delete it: `{tag, repo_root, asked_at}`, or null when there is none to keep. */
export function takeEngineFollow(userData, { now = Date.now(), fsApi = fs } = {}) {
  if (!userData) return null;
  const file = followPath(userData);
  let raw;
  try {
    raw = fsApi.readFileSync(file, 'utf8');
  } catch {
    return null; // no promise: the ordinary launch
  }
  try {
    fsApi.rmSync(file, { force: true });
  } catch (err) {
    console.warn('[nova-update] could not delete the backend promise', err);
  }
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    return null; // unreadable: never guessed
  }
  if (!body || body.schema_version !== ENGINE_FOLLOW_SCHEMA_VERSION || !TAG_RE.test(String(body.tag ?? ''))) return null;
  const at = Number(body.asked_at);
  if (!Number.isFinite(at) || now - at > ENGINE_FOLLOW_MAX_AGE_MS || at > now + 60_000) return null;
  return { tag: body.tag, repo_root: typeof body.repo_root === 'string' ? body.repo_root : null, asked_at: at };
}

/**
 * What GET /api/diagnostics/restart-check says a restart would interrupt: `{safe, lines}`, where
 * `safe` is true only when the backend answered and nothing is open. A backend too old to answer
 * reads as unknown, never as nothing open.
 */
export function restartCheckLines(body) {
  if (!body || typeof body !== 'object' || body.schema_version !== 1) {
    return { safe: null, lines: ['The backend did not say what is open: check your positions and recordings.'] };
  }
  const open = Array.isArray(body.open)
    ? body.open.map((row) => (row && typeof row.text === 'string' && row.text ? row.text : null)).filter(Boolean)
    : [];
  const unknown = Array.isArray(body.unknown)
    ? body.unknown.map((row) => `Could not read ${String(row?.kind ?? 'something')}: ${String(row?.error ?? 'unknown error')}`)
    : [];
  return { safe: body.safe === true ? true : body.safe === false ? false : null, lines: [...open, ...unknown] };
}

/** Restart to update, with something open on the backend: button 0 updates both, 1 (the default) waits. */
export function openNowPrompt(tag, lines) {
  return {
    type: 'warning',
    title: 'Update Nova',
    message: `Updating to ${tag} restarts the backend too.`,
    detail: `Open now:\n${lines.map((line) => `- ${line}`).join('\n')}\n\nThe backend comes back in about half a minute.`,
    buttons: ['Update Nova', 'Not now'],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  };
}

/** The backend's checkout cannot come along: button 0 (the default) waits, 1 updates the desk alone. */
export function cannotFollowPrompt(tag, reason) {
  return {
    type: 'warning',
    title: 'Update Nova',
    message: `The backend cannot be updated to ${tag}.`,
    detail: `${reason}.\n\nUpdating the desk alone leaves the two on different versions until the backend is updated.`,
    buttons: ['Not now', 'Update the desk only'],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  };
}
