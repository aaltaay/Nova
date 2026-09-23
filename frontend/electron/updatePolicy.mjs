/**
 * In-app update policy (#347) -- pure: no Electron, no electron-updater, no I/O.
 *
 * The installed desk downloads a newer installer in the background, then asks.
 * It never installs or restarts on its own: not on quit, not on a timer, not
 * after a failed check. Installing is one operator click, "Restart to update".
 *
 * autoUpdate.mjs owns the electron-updater instance and feeds its events through
 * reduceUpdateState(); every decision about what to show or do lives here.
 */
import { releaseTagFromText } from './releaseTag.mjs';

/** Desk setting (process env or the desk .env). `0` / `false` / `no` / `off` stops automatic checks. */
export const UPDATE_CHECK_ENV = 'NOVA_UPDATE_CHECK';
/** Let the desk finish starting (engine, Gateway attach) before touching the network. */
export const UPDATE_FIRST_CHECK_DELAY_MS = 15_000;

export const RESTART_BUTTON = 0;
export const LATER_BUTTON = 1;

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
 * phase: idle | checking | downloading | ready | current | failed | installing.
 * `failedStage` says which step a `failed` phase failed in: `check` (asking
 * GitHub for the latest release) or `download` (fetching the installer, whose
 * part is kept for Resume). `retry` is the chunk retry in progress while
 * downloading, 0 when none. `promptedVersion` remembers the version already
 * offered this session, so Later is not re-asked until the next launch or an
 * explicit Help-menu request.
 */
export const INITIAL_UPDATE_STATE = Object.freeze({
  phase: 'idle',
  version: '',
  percent: 0,
  error: '',
  failedStage: '',
  retry: 0,
  promptedVersion: '',
});

function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, n));
}

export function reduceUpdateState(state, event) {
  const ready = state.phase === 'ready';
  switch (event?.type) {
    case 'checking':
      // An installer already on disk stays offered; a re-check cannot lose it.
      return ready ? state : { ...state, phase: 'checking', error: '', failedStage: '', retry: 0 };
    case 'available':
      return { ...state, phase: 'downloading', version: String(event.version || ''), percent: 0, error: '', retry: 0 };
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
      if (ready) return { ...state, error: errorText(event.message) };
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
    case 'prompted':
      return { ...state, promptedVersion: String(event.version || '') };
    case 'installing':
      return ready ? { ...state, phase: 'installing', error: '' } : state;
    case 'install-failed':
      // The downloaded installer is still cached; the operator can try again.
      return { ...state, phase: 'ready', error: errorText(event.message) };
    default:
      return state;
  }
}

/** Offer the restart once per version per session. */
export function shouldPromptRestart(state) {
  return state.phase === 'ready' && Boolean(state.version) && state.promptedVersion !== state.version;
}

/** The startup check: only when allowed and nothing is already in hand or in flight. */
export function shouldAutoCheck(state, gate) {
  if (!gate?.updater || !gate.automatic) return false;
  return state.phase !== 'ready' && !BUSY_PHASES.has(state.phase);
}

/** Help > Check for Updates: re-offer a ready installer, else check unless busy. */
export function manualCheckAction(state, gate) {
  if (!gate?.updater) return 'unavailable';
  if (state.phase === 'ready') return 'prompt';
  if (BUSY_PHASES.has(state.phase)) return 'busy';
  return 'check';
}

/** Taskbar progress: a fraction while downloading, -1 (cleared) otherwise. */
export function taskbarProgress(state) {
  return state.phase === 'downloading' ? clampPercent(state.percent) / 100 : -1;
}

/**
 * Help-menu rows. `action` is 'check' | 'restart'; rows without one are status
 * text (disabled). The installed version is always visible.
 */
export function updateMenuItems(state, { currentTag = '', automatic = true } = {}) {
  const tag = displayTag(state.version);
  const rows = [];
  switch (state.phase) {
    case 'checking':
      rows.push({ label: 'Checking for updates…' });
      break;
    case 'downloading':
      rows.push({ label: `Downloading ${tag}… ${Math.round(clampPercent(state.percent))}%` });
      if (state.retry) rows.push({ label: `Connection dropped; retrying (attempt ${state.retry})` });
      break;
    case 'ready':
      rows.push({ label: `Restart to Update (${tag})`, action: 'restart' });
      if (state.error) rows.push({ label: `Last attempt failed: ${state.error}` });
      break;
    case 'installing':
      rows.push({ label: `Installing ${tag}…` });
      break;
    case 'failed':
      if (state.failedStage === 'download') {
        const pct = Math.floor(clampPercent(state.percent));
        rows.push({ label: `Download of ${tag} stopped at ${pct}% — Resume`, action: 'check' });
      } else {
        rows.push({ label: 'Update check failed — Retry', action: 'check' });
      }
      rows.push({ label: state.error || 'unknown error' });
      break;
    case 'current':
      rows.push({ label: 'Check for Updates…', action: 'check' });
      rows.push({ label: 'This is the latest release' });
      break;
    default:
      rows.push({ label: 'Check for Updates…', action: 'check' });
  }
  if (currentTag) rows.push({ label: `Installed: Nova ${currentTag}` });
  if (!automatic) rows.push({ label: `Automatic checks off (${UPDATE_CHECK_ENV})` });
  return rows;
}

/** The ready prompt. Later is the default so a stray Enter never restarts the desk. */
export function restartPrompt(version) {
  const tag = displayTag(version);
  return {
    type: 'info',
    title: 'Nova update ready',
    message: `Nova ${tag} is downloaded and ready to install.`,
    detail:
      'Restart to update closes Nova and its local engine, installs the update, then reopens Nova. '
      + 'Later keeps this session running and installs nothing; use Help > Restart to Update when you are ready.',
    buttons: ['Restart to update', 'Later'],
    defaultId: LATER_BUTTON,
    cancelId: LATER_BUTTON,
    noLink: true,
  };
}

export function isRestartChoice(response) {
  return response === RESTART_BUTTON;
}

/** What a Help-menu check reports once it settles (automatic checks stay quiet). */
export function manualCheckResult(state, currentTag = '') {
  if (state.phase === 'current') {
    return {
      type: 'info',
      message: currentTag ? `Nova ${currentTag} is the latest release.` : 'Nova is up to date.',
    };
  }
  if (state.phase === 'failed' && state.failedStage === 'download') {
    return {
      type: 'warning',
      message: `Nova could not finish downloading ${displayTag(state.version)}.`,
      detail:
        `${state.error}\n\nWhat already arrived is kept. Nova keeps running on its current version; `
        + 'Help > Resume continues the download from where it stopped.',
    };
  }
  if (state.phase === 'failed') {
    return {
      type: 'warning',
      message: 'Nova could not check for updates.',
      detail: `${state.error}\n\nNova keeps running on its current version. Try again from Help > Check for Updates.`,
    };
  }
  return null;
}
