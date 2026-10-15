/**
 * The automatic download and install (operator ask 2026-10-14: "I want an auto update").
 *
 * A newer release goes by itself, but only when nothing is at stake: outside weekday trading hours
 * (the 150 MB download shares the desk's link with the market data), while the backend's restart
 * check lists nothing but recordings -- read exactly as the backend's own automatic restart reads it
 * (engineFollow.autoRestartHolds: a backend that does not answer holds it too) -- and, for the
 * install, once Windows has seen no keyboard or mouse input for UPDATE_AUTO_IDLE_MS. What it waits
 * for is on the desk's notice (`state.auto`). The download and the install are the operator's own
 * (Update, Restart to update) without a dialog; an install that cannot go ahead for anything but a
 * hold leaves that version to the operator's click for the session. When it may go is decided here;
 * autoUpdate.mjs looks every UPDATE_AUTO_TICK_MS and after each check.
 */
import { AUTO_RESTART_NO_ANSWER } from './engineFollow.mjs';
import {
  AUTO_WAIT_IDLE,
  AUTO_WAIT_TRADING_HOURS,
  UPDATE_AUTO_IDLE_MS,
  autoAllowed,
  displayTag,
  errorText,
  inUpdateQuietHours,
} from './updatePolicy.mjs';

/**
 * @param {{ getState: () => any, dispatch: (event: object) => void, enabled: () => boolean,
 *   holds: () => Promise<string[] | null>, idleMs: () => number, download: () => Promise<void>,
 *   install: () => Promise<boolean>, logger: { info: Function, warn: Function }, now?: () => number }} deps
 */
export function createAutoInstall({ getState, dispatch, enabled, holds, idleMs, download, install, logger, now = Date.now }) {
  let busy = false;
  // A version an automatic install could not prepare: the operator's click from then on.
  let leftVersion = '';
  let lastLogged = '';

  /** What holds it on the backend; an answer that cannot be read holds it, never "nothing open". */
  async function readHolds() {
    try {
      const lines = await holds();
      return Array.isArray(lines) ? lines.map(String) : [AUTO_RESTART_NO_ANSWER];
    } catch (err) {
      return [`Could not read what is open: ${errorText(err)}`];
    }
  }

  function readIdleMs() {
    try {
      const ms = Number(idleMs());
      return Number.isFinite(ms) ? ms : 0;
    } catch (err) {
      logger.warn(`cannot read keyboard and mouse idle time: ${errorText(err)}`);
      return 0; // unknown reads as in use: never installs under the operator's hands
    }
  }

  /** What it waits for now: null when the release is the operator's, [] when it goes now. */
  async function waiting() {
    const state = getState();
    if (!autoAllowed(state, { enabled: enabled(), leftVersion })) return null;
    if (inUpdateQuietHours(now())) return [AUTO_WAIT_TRADING_HOURS];
    const lines = await readHolds();
    if (state.phase === 'ready' && readIdleMs() < UPDATE_AUTO_IDLE_MS) lines.push(AUTO_WAIT_IDLE);
    return lines;
  }

  function show(list) {
    const auto = list ? { waiting: list } : null;
    const state = getState();
    if (JSON.stringify(state.auto) !== JSON.stringify(auto)) dispatch({ type: 'auto', auto });
    const key = JSON.stringify([state.version, state.phase, list]);
    if (list?.length && key !== lastLogged) {
      logger.info(`${displayTag(state.version)} ${state.phase === 'ready' ? 'installs' : 'downloads'} by itself once clear; waiting for: ${list.join('; ')}`);
    }
    lastLogged = key;
  }

  /** Look once: download or install now when nothing holds it. True when it started one. */
  async function step() {
    if (busy) return false;
    busy = true;
    try {
      const { phase, version } = getState();
      const list = await waiting();
      // A click or a check moved the release while the backend answered: the next look decides.
      if (getState().phase !== phase || getState().version !== version) return false;
      show(list);
      if (!list || list.length) return false;
      if (phase === 'available') {
        logger.info(`downloading ${displayTag(version)} by itself: outside trading hours, nothing open`);
        await download();
        // Downloaded: the notice says at once what the install waits for, not only at the next look.
        if (getState().phase === 'ready') show(await waiting());
        return true;
      }
      if (phase !== 'ready') return false;
      logger.info(`installing ${displayTag(version)} by itself: outside trading hours, nothing open, `
        + `no keyboard or mouse input for ${Math.floor(readIdleMs() / 60_000)} min`);
      if (await install()) return true;
      if (getState().phase !== 'ready') return false;
      // A trade placed while the backend was prepared waits for the next look; anything else is the operator's.
      const late = await readHolds();
      if (late.length) {
        show(late);
        return false;
      }
      leftVersion = version;
      show(null);
      logger.warn(`${displayTag(version)} left to Restart to update: the install could not go ahead by itself (see above)`);
      return false;
    } finally {
      busy = false;
    }
  }

  return { step, waiting };
}
