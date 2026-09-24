/**
 * What the in-app updater says (#347) -- pure: the Help-menu rows and the
 * native dialogs. The desk's own notice and What's new card are the renderer's
 * (frontend/src/desktop_update/); these are what the main process shows itself:
 * the menu always, a dialog when the operator asked from the menu or when the
 * window cannot show the notice. When to say it lives in updatePolicy.mjs.
 */
import { UPDATE_CHECK_ENV, clampPercent, displayTag } from './updatePolicy.mjs';

export const RESTART_BUTTON = 0;
export const UPDATE_BUTTON = 0;
export const LATER_BUTTON = 1;

/**
 * Help-menu rows. `action` is 'check' | 'download' | 'restart' | 'whats-new';
 * rows without one are status text (disabled). The installed version is always
 * visible, with its release notes one click away.
 */
export function updateMenuItems(state, { currentTag = '', automatic = true } = {}) {
  const tag = displayTag(state.version);
  const rows = [];
  switch (state.phase) {
    case 'checking':
      rows.push({ label: 'Checking for updates…' });
      break;
    case 'available':
      rows.push({ label: `Update to ${tag}…`, action: 'download' });
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
  if (currentTag) {
    rows.push({ label: `What's New in Nova ${currentTag}…`, action: 'whats-new' });
    rows.push({ label: `Installed: Nova ${currentTag}` });
  }
  if (!automatic) rows.push({ label: `Automatic checks off (${UPDATE_CHECK_ENV})` });
  return rows;
}

/**
 * The found-release question, for a desk whose window cannot show the notice.
 * Later is the default so a stray Enter never starts a 150 MB download.
 */
export function availablePrompt(version, currentTag = '', notes = '') {
  const tag = displayTag(version);
  const since = currentTag ? ` (you have ${currentTag})` : '';
  const what = notes ? `What's new:\n${notes}\n\n` : '';
  return {
    type: 'info',
    title: 'Nova update available',
    message: `Nova ${tag} is available${since}.`,
    detail:
      `${what}Update downloads it now; nothing restarts until you choose Restart to update. `
      + 'Later keeps this version; Help > Check for Updates offers it again.',
    buttons: ['Update', 'Later'],
    defaultId: LATER_BUTTON,
    cancelId: LATER_BUTTON,
    noLink: true,
  };
}

export function isUpdateChoice(response) {
  return response === UPDATE_BUTTON;
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
