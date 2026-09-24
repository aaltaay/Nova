/**
 * In-app update policy (#347) -- pure: no Electron, no electron-updater, no I/O.
 *
 * The installed desk checks for a newer release and tells the operator, with its
 * release notes, in a notice on the desk (operator ask, 2026-09-23). Nothing
 * downloads until the operator picks Update; nothing installs until they pick
 * Restart to update. It never installs or restarts on its own: not on quit, not
 * on a timer, not after a failed check. It checks shortly after launch and again
 * every two hours while it stays open, except in weekday trading hours, when a
 * re-check neither downloads nor asks.
 *
 * autoUpdate.mjs owns the electron-updater instance and feeds its events through
 * reduceUpdateState(); every decision about what to show or do lives here, and
 * what the Help menu and the dialogs say lives in updateCopy.mjs.
 */
import { releaseTagFromText } from './releaseTag.mjs';

/** Desk setting (process env or the desk .env). `0` / `false` / `no` / `off` stops automatic checks. */
export const UPDATE_CHECK_ENV = 'NOVA_UPDATE_CHECK';
/** Let the desk finish starting (engine, Gateway attach) before touching the network. */
export const UPDATE_FIRST_CHECK_DELAY_MS = 15_000;
/** While the desk stays open, ask GitHub again this often. */
export const UPDATE_RECHECK_INTERVAL_MS = 2 * 60 * 60_000;
/** How often the open desk looks whether a re-check, or a held prompt, is due. */
export const UPDATE_RECHECK_TICK_MS = 10 * 60_000;
/**
 * Weekday trading hours on the Eastern clock, as minutes of the day: the
 * premarket window's open (07:00, ADR 027) to the regular close (16:00). A
 * re-check neither downloads nor asks in them -- the 150 MB download shares the
 * desk's link with the market data, and the prompt takes keyboard focus, so a
 * hotkey pressed mid-trade would land in it.
 */
export const UPDATE_QUIET_START_MIN_ET = 7 * 60;
export const UPDATE_QUIET_END_MIN_ET = 16 * 60;

const OFF_VALUES = new Set(['0', 'false', 'no', 'off']);
const BUSY_PHASES = new Set(['checking', 'downloading', 'installing']);
const ERROR_TEXT_MAX = 160;

/** Automatic checks stay on unless the operator switched them off. */
export function updateCheckSetting(raw) {
  return !OFF_VALUES.has(String(raw ?? '').trim().toLowerCase());
}

/** The process env wins (like every other desk flag); else the desk .env value. */
export function resolveUpdateSetting({ processValue, fileValue } = {}) {
  const fromProcess = String(processValue ?? '').trim();
  return fromProcess || String(fileValue ?? '').trim();
}

/**
 * Can this process update itself, and may it check without being asked?
 * `updater`: a packaged Windows (NSIS) install -- a dev checkout never updates.
 * `automatic`: the startup check runs. The Help menu check needs only `updater`.
 */
export function updateGate({ isPackaged, platform, setting } = {}) {
  if (!isPackaged) {
    return { updater: false, automatic: false, reason: 'dev build (not packaged)' };
  }
  if (platform !== 'win32') {
    return { updater: false, automatic: false, reason: `installer updates are Windows-only (${platform})` };
  }
  if (!updateCheckSetting(setting)) {
    return { updater: true, automatic: false, reason: `${UPDATE_CHECK_ENV} is off` };
  }
  return { updater: true, automatic: true, reason: '' };
}

/** `0.1.832` -> `v832`; anything else is shown as given. */
export function displayTag(version) {
  return releaseTagFromText(version) || String(version ?? '').trim();
}

export function errorText(err) {
  const raw = err instanceof Error ? err.message : String(err ?? '');
  const firstLine = raw.split(/\r?\n/).find((line) => line.trim()) || 'unknown error';
  const line = firstLine.trim();
  return line.length > ERROR_TEXT_MAX ? `${line.slice(0, ERROR_TEXT_MAX - 1)}…` : line;
}

/**
 * phase: idle | checking | available | downloading | ready | current | failed | installing.
 * `available`: a newer release was found and nothing is downloaded until the
 * operator picks Update. `failedStage` says which step a `failed` phase failed
 * in: `check` (asking GitHub for the latest release) or `download` (fetching the
 * installer, whose part is kept for Resume). `retry` is the chunk retry in
 * progress while downloading, 0 when none.
 *
 * The notice: `offeredVersion` is the version the desk has told the operator
 * about this session, `dismissedVersion` the one they answered Later for (not
 * raised again until the next launch or a Help-menu request), and
 * `consentVersion` the one they picked Update for -- a download of it that
 * stopped is resumed without asking again.
 */
export const INITIAL_UPDATE_STATE = Object.freeze({
  phase: 'idle',
  version: '',
  percent: 0,
  error: '',
  failedStage: '',
  retry: 0,
  offeredVersion: '',
  dismissedVersion: '',
  consentVersion: '',
});

export function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, n));
}

function stoppedDownload(state) {
  return state.phase === 'failed' && state.failedStage === 'download';
}

export function reduceUpdateState(state, event) {
  const ready = state.phase === 'ready';
  // An installer on disk, or a release on offer, survives a re-check that runs or fails.
  const held = ready || state.phase === 'available';
  switch (event?.type) {
    case 'checking':
      return held ? state : { ...state, phase: 'checking', error: '', failedStage: '', retry: 0 };
    case 'available': {
      if (ready) return state;
      const version = String(event.version || '');
      // The same version's stopped download keeps its percent for Resume.
      const percent = version === state.version ? state.percent : 0;
      return { ...state, phase: 'available', version, percent, error: '', failedStage: '', retry: 0 };
    }
    case 'download': {
      // The operator picked Update (or Resume) for the version on offer; the
      // notice follows its download even if it was hidden with Later.
      if (state.phase !== 'available' && !stoppedDownload(state)) return state;
      const { version } = state;
      return {
        ...state,
        phase: 'downloading',
        consentVersion: version,
        offeredVersion: version,
        dismissedVersion: '',
        error: '',
        failedStage: '',
        retry: 0,
      };
    }
    case 'not-available':
      return ready ? state : { ...state, phase: 'current', percent: 0, error: '' };
    case 'progress':
      return state.phase === 'downloading' ? { ...state, percent: clampPercent(event.percent), retry: 0 } : state;
    case 'retrying':
      return state.phase === 'downloading' ? { ...state, retry: Math.max(1, Number(event.attempt) || 1) } : state;
    case 'downloaded':
      return {
        ...state,
        phase: 'ready',
        version: String(event.version || state.version),
        percent: 100,
        error: '',
      };
    case 'error': {
      if (held) return { ...state, error: errorText(event.message) };
      // A download that stopped keeps its percent: Resume continues from there.
      const download = state.phase === 'downloading';
      return {
        ...state,
        phase: 'failed',
        failedStage: download ? 'download' : 'check',
        percent: download ? state.percent : 0,
        retry: 0,
        error: errorText(event.message),
      };
    }
    case 'offered':
      return { ...state, offeredVersion: String(event.version || '') };
    case 'dismissed':
      return { ...state, dismissedVersion: String(event.version || '') };
    case 'reoffer':
      // A Help-menu request: raise the notice again even after Later.
      return { ...state, offeredVersion: '', dismissedVersion: '' };
    case 'installing':
      return ready ? { ...state, phase: 'installing', error: '' } : state;
    case 'install-failed':
      // The downloaded installer is still cached; the operator can try again.
      return { ...state, phase: 'ready', error: errorText(event.message) };
    default:
      return state;
  }
}

/** The startup check: only when allowed and nothing is already in hand or in flight. */
export function shouldAutoCheck(state, gate) {
  if (!gate?.updater || !gate.automatic) return false;
  return state.phase !== 'ready' && !BUSY_PHASES.has(state.phase);
}

const EASTERN = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York',
  weekday: 'short',
  hour: 'numeric',
  minute: 'numeric',
  hourCycle: 'h23',
});

/** Weekday (`Mon`..`Sun`) and minute of the day on the Eastern clock. */
export function easternClock(nowMs) {
  const parts = {};
  for (const part of EASTERN.formatToParts(new Date(nowMs))) parts[part.type] = part.value;
  return { weekday: parts.weekday, minute: Number(parts.hour) * 60 + Number(parts.minute) };
}

/** Weekday 07:00-16:00 ET. A holiday is not special: it only delays a re-check. */
export function inUpdateQuietHours(nowMs) {
  const { weekday, minute } = easternClock(nowMs);
  if (weekday === 'Sat' || weekday === 'Sun') return false;
  return minute >= UPDATE_QUIET_START_MIN_ET && minute < UPDATE_QUIET_END_MIN_ET;
}

/** A re-check while the desk stays open: as the startup check allows, once per interval, never in trading hours. */
export function shouldRecheck(state, gate, { now, lastCheckAt } = {}) {
  if (!shouldAutoCheck(state, gate) || inUpdateQuietHours(now)) return false;
  return now - (Number(lastCheckAt) || 0) >= UPDATE_RECHECK_INTERVAL_MS;
}

/** A found (or downloaded) release the operator has not been told about this session. */
export function needsOffer(state) {
  if (state.phase !== 'available' && state.phase !== 'ready') return false;
  const { version } = state;
  return Boolean(version) && state.offeredVersion !== version && state.dismissedVersion !== version;
}

/**
 * Raise the notice now? A launch or Help-menu check tells the operator at once
 * (they are starting up, or asked); a re-check's find waits out trading hours.
 * `origin`: 'launch' | 'manual' | 'recheck'.
 */
export function shouldOfferNow(state, { origin, now } = {}) {
  if (!needsOffer(state)) return false;
  return origin !== 'recheck' || !inUpdateQuietHours(now);
}

/** A found release the operator already chose Update for (its download stopped): resume, no question. */
export function hasConsent(state) {
  return state.phase === 'available' && Boolean(state.version) && state.consentVersion === state.version;
}

/**
 * Help > Check for Updates: raise the notice again for a release already found
 * ('offer') or downloaded ('prompt'), else check unless busy.
 */
export function manualCheckAction(state, gate) {
  if (!gate?.updater) return 'unavailable';
  if (state.phase === 'ready') return 'prompt';
  if (state.phase === 'available') return 'offer';
  if (BUSY_PHASES.has(state.phase)) return 'busy';
  return 'check';
}

/**
 * What the desk's update notice shows, or null when it shows nothing. It
 * appears once the version was offered, follows it through the download, and
 * hides after Later. `stage`: available | downloading | stopped | ready | installing.
 */
export function noticeFor(state) {
  const { version } = state;
  if (!version || state.offeredVersion !== version) return null;
  const stage = {
    available: 'available',
    downloading: 'downloading',
    ready: 'ready',
    installing: 'installing',
    failed: stoppedDownload(state) ? 'stopped' : '',
  }[state.phase];
  // Installing is the operator's own click; it shows even after an earlier Later.
  if (!stage || (stage !== 'installing' && state.dismissedVersion === version)) return null;
  return {
    stage,
    tag: displayTag(version),
    percent: Math.floor(clampPercent(state.percent)),
    retry: stage === 'downloading' ? state.retry : 0,
    error: stage === 'stopped' || stage === 'ready' ? state.error : '',
  };
}

/** Taskbar progress: a fraction while downloading, -1 (cleared) otherwise. */
export function taskbarProgress(state) {
  return state.phase === 'downloading' ? clampPercent(state.percent) / 100 : -1;
}
