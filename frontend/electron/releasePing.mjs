/**
 * GitHub's release ping (operator ask 2026-10-14: "If a new release goes up in the cloud, how can
 * the cloud communicate with us").
 *
 * GitHub cannot call the desk: it has no public address, and its API answers 127.0.0.1 only. So
 * `Desktop pack` posts each published `vNNN` to a public ntfy.sh topic, and the desk keeps one
 * outgoing connection to it -- ntfy's JSON stream, one event per line. A ping is a hint, never a
 * source: it only makes the desk ask GitHub now (autoUpdate.mjs), and the installer still comes from
 * the Release, checked against its sha512. Anyone can post to a public topic; a false ping costs one
 * check, and the checks pings cause are spaced out by the caller.
 *
 * A connection that drops, or goes silent past ntfy's keepalive, is opened again -- after 5 s at
 * first, doubling to 5 min -- and asks for what was posted since the last event it read, so a release
 * that went out meanwhile still arrives. Nothing is persisted. Schema:
 * architecture/schema/desk-ops.md, "Release notes and the update notice".
 */
import { releaseTagFromText } from './releaseTag.mjs';

export const RELEASE_PING_SERVER = 'https://ntfy.sh';
/** `Desktop pack` posts here (.github/workflows/desktop-pack.yml); a test holds the two to one name. */
export const RELEASE_PING_TOPIC = 'nova-aaltaay-desk-releases';
/** ntfy.sh sends a keepalive every 45 s: a connection silent this long is dead. */
export const RELEASE_PING_SILENT_MS = 3 * 60_000;
export const RELEASE_PING_RETRY_MIN_MS = 5_000;
export const RELEASE_PING_RETRY_MAX_MS = 5 * 60_000;

/** The stream to read; `since` (epoch seconds) asks again for what was posted from then on. */
export function releasePingUrl(since) {
  const url = `${RELEASE_PING_SERVER}/${RELEASE_PING_TOPIC}/json`;
  return Number.isFinite(since) && since > 0 ? `${url}?since=${Math.floor(since)}` : url;
}

/**
 * One line of the stream: `{time, tag}` -- `tag` the `vNNN` a release ping names, '' for every other
 * event (open, keepalive) or message -- or null for a line that is not an ntfy event.
 */
export function readPingLine(line) {
  const text = String(line ?? '').trim();
  if (!text) return null;
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return null; // not an event: the stream carries nothing else worth reading
  }
  if (!body || typeof body !== 'object' || typeof body.event !== 'string') return null;
  const time = Number(body.time);
  const tag = body.event === 'message' ? releaseTagFromText(String(body.message ?? '')) : '';
  return { time: Number.isFinite(time) ? time : 0, tag };
}

function errorText(err) {
  const raw = err instanceof Error ? err.message : String(err ?? '');
  return raw.split(/\r?\n/)[0].trim() || 'unknown error';
}

/**
 * @param {{ fetch: (url: string, init: object) => Promise<any>, onRelease: (tag: string) => void,
 *   logger: { info: Function, warn: Function }, setTimer?: Function, clearTimer?: Function }} deps
 */
export function createReleasePing({ fetch, onRelease, logger, setTimer = setTimeout, clearTimer = clearTimeout }) {
  let stopped = true;
  let controller = null;
  let retryTimer = null;
  let silentTimer = null;
  let retryMs = RELEASE_PING_RETRY_MIN_MS;
  // Epoch seconds of the last event read: a reopened connection asks from there.
  let lastTime = 0;
  let listening = false;
  // A run of failed connections is logged once, and its end once.
  let failing = false;

  function timer(fn, ms) {
    const t = setTimer(fn, ms);
    t?.unref?.();
    return t;
  }

  function watchSilence() {
    if (silentTimer) clearTimer(silentTimer);
    silentTimer = timer(() => controller?.abort(new Error('no keepalive for 3 minutes')), RELEASE_PING_SILENT_MS);
  }

  function read(line) {
    const event = readPingLine(line);
    if (!event) return;
    if (event.time) lastTime = event.time;
    if (!listening) {
      listening = true;
      retryMs = RELEASE_PING_RETRY_MIN_MS;
      if (failing) logger.info('release ping connection is back');
      else logger.info(`listening for release pings on ${RELEASE_PING_SERVER}/${RELEASE_PING_TOPIC}`);
      failing = false;
    }
    if (event.tag) onRelease(event.tag);
  }

  async function connect() {
    retryTimer = null;
    if (stopped) return;
    controller = new AbortController();
    listening = false;
    watchSilence();
    let reason = 'the connection ended';
    try {
      const res = await fetch(releasePingUrl(lastTime), { signal: controller.signal });
      if (!res?.ok || typeof res.body?.getReader !== 'function') throw new Error(`HTTP ${res?.status ?? '?'}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        watchSilence();
        pending += decoder.decode(value, { stream: true });
        const lines = pending.split('\n');
        pending = lines.pop() ?? '';
        lines.forEach(read);
      }
    } catch (err) {
      reason = errorText(controller.signal.reason ?? err);
    } finally {
      if (silentTimer) clearTimer(silentTimer);
      silentTimer = null;
    }
    if (stopped) return;
    if (!failing) logger.warn(`release ping connection lost (${reason}); trying again, the desk's own checks still run`);
    failing = true;
    retryTimer = timer(() => void connect(), retryMs);
    retryMs = Math.min(retryMs * 2, RELEASE_PING_RETRY_MAX_MS);
  }

  return {
    start() {
      if (!stopped) return;
      stopped = false;
      void connect();
    },
    stop() {
      stopped = true;
      if (retryTimer) clearTimer(retryTimer);
      retryTimer = null;
      controller?.abort(new Error('stopped'));
    },
  };
}
