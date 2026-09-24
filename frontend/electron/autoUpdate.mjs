/**
 * In-app updates (#347): electron-updater reading this repo's GitHub Releases.
 *
 * A check that finds a newer release tells the operator, with that release's
 * notes, in a notice on the desk: Update / Later (operator ask, 2026-09-23).
 * Nothing downloads until Update, and nothing installs until Restart to update.
 * autoInstallOnAppQuit is off, the only timer re-checks (every two hours while
 * the desk stays open, never in weekday trading hours), and a failed check or
 * download only changes the Help menu. After an update, the first launch shows
 * What's new (whatsNew.mjs). Decisions live in updatePolicy.mjs, words in
 * updateCopy.mjs, reaching the operator (notice, Help menu, dialogs) in
 * updateAsk.mjs, the renderer link in updateBridge.mjs; this file is the
 * wiring around electron-updater.
 *
 * electron-updater checks and installs; the installer itself is fetched in
 * resumable chunks (releaseDownload.mjs) and handed back through electron-updater's
 * cache, because its own one-shot download never finished on a lossy link.
 * Every line of this is also written to update.log (updateLog.mjs).
 *
 * electron-updater loads lazily and only in a packaged Windows build, so a dev
 * checkout never loads it. Every failure here is logged and swallowed -- the desk
 * keeps running on the version it has.
 */
import fs from 'node:fs';
import { app, ipcMain, net, shell } from 'electron';
import { readEnvValue } from './envMerge.mjs';
import { downloadRelease } from './releaseDownload.mjs';
import { isReleaseLink, notesText } from './releaseNotes.mjs';
import { createNotesSource } from './releaseNotesSource.mjs';
import { createUpdateAsk } from './updateAsk.mjs';
import { createUpdateBridge } from './updateBridge.mjs';
import {
  availablePrompt,
  isRestartChoice,
  isUpdateChoice,
  manualCheckResult,
  restartPrompt,
  updateMenuItems,
} from './updateCopy.mjs';
import { createUpdateLogger } from './updateLog.mjs';
import {
  INITIAL_UPDATE_STATE,
  UPDATE_CHECK_ENV,
  UPDATE_FIRST_CHECK_DELAY_MS,
  UPDATE_RECHECK_TICK_MS,
  displayTag,
  errorText,
  hasConsent,
  manualCheckAction,
  needsOffer,
  reduceUpdateState,
  resolveUpdateSetting,
  shouldAutoCheck,
  shouldOfferNow,
  shouldRecheck,
  taskbarProgress,
  updateGate,
} from './updatePolicy.mjs';
import { createWhatsNew } from './whatsNew.mjs';

function appDir(name) {
  try {
    return app.getPath(name);
  } catch {
    return '';
  }
}

const logger = createUpdateLogger({ prefix: '[nova-update]', dir: () => appDir('logs') });

let updater = null;
let gate = { updater: false, automatic: false, reason: 'not started' };
let state = INITIAL_UPDATE_STATE;
let manualPending = false;
// Which check is running ('launch' | 'manual' | 'recheck') and when the last one began.
let checkOrigin = 'launch';
let lastCheckAt = 0;
let currentTag = '';
let bridge = null;
let ask = null;
let whatsNew = null;
// The release on offer: electron-updater's info from the check that found it.
let pendingInfo = null;
let hooks = {
  getWindow: () => null,
  envPath: () => '',
  stopEngine: async () => true,
  restartEngine: async () => {},
};

function readSetting() {
  let fileValue = '';
  const envPath = hooks.envPath();
  try {
    if (envPath && fs.existsSync(envPath)) {
      fileValue = readEnvValue(fs.readFileSync(envPath, 'utf8'), UPDATE_CHECK_ENV);
    }
  } catch (err) {
    logger.warn(`cannot read ${UPDATE_CHECK_ENV} from ${envPath}: ${errorText(err)}`);
  }
  return resolveUpdateSetting({ processValue: process.env[UPDATE_CHECK_ENV], fileValue });
}

function liveWindow() {
  const win = hooks.getWindow();
  return win && !win.isDestroyed() ? win : null;
}

function renderMenu() {
  ask?.setMenu(updateMenuItems(state, { currentTag, automatic: gate.automatic }), {
    restart: () => void restartToUpdate(),
    check: () => void checkNow('manual'),
    download: () => void startDownload(),
    'whats-new': () => void whatsNew?.openRecent(),
  });
}

function dispatch(event) {
  state = reduceUpdateState(state, event);
  renderMenu();
  const win = liveWindow();
  if (win) win.setProgressBar(taskbarProgress(state));
  ask?.publish();
}

async function reportManualResult() {
  if (!manualPending) return;
  const result = manualCheckResult(state, currentTag);
  if (!result) return;
  manualPending = false;
  await ask.box({ title: 'Nova updates', buttons: ['OK'], noLink: true, ...result });
}

/**
 * Tell the operator about the release on offer (found, or already downloaded):
 * the desk's notice, or a dialog when the window cannot show one.
 */
async function offer() {
  const { version, phase } = state;
  if (!version || (phase !== 'available' && phase !== 'ready')) return;
  dispatch({ type: 'offered', version });
  const notes = ask.notesFor(displayTag(version));
  if (bridge.hasListener()) {
    ask.attention();
    return;
  }
  if (phase === 'ready') {
    await promptRestart();
    return;
  }
  const { releases } = await notes;
  if (isUpdateChoice(await ask.ask(availablePrompt(version, currentTag, notesText(releases))))) {
    await startDownload();
  } else {
    later();
  }
}

function later() {
  if (!state.version) return;
  logger.info(`${displayTag(state.version)} postponed by operator`);
  dispatch({ type: 'dismissed', version: state.version });
}

async function promptRestart() {
  if (isRestartChoice(await ask.ask(restartPrompt(state.version)))) await restartToUpdate();
  else later();
}

/** Update (or Resume): download the release on offer. A stopped download is re-checked first. */
async function startDownload() {
  if (!updater) return;
  if (state.phase === 'failed' && state.failedStage === 'download') {
    // The check finds the same release and resumes it: the operator already chose it.
    await checkNow('manual');
    return;
  }
  if (state.phase !== 'available' || !pendingInfo) return;
  dispatch({ type: 'download' });
  logger.info(`downloading ${displayTag(state.version)} at the operator's request`);
  await fetchUpdate(pendingInfo);
}

async function recoverEngine() {
  try {
    await hooks.restartEngine();
  } catch (err) {
    logger.error(`engine restart after a failed install: ${errorText(err)}`);
  }
}

async function restartToUpdate() {
  if (!updater || state.phase !== 'ready') return;
  dispatch({ type: 'installing' });
  let stopped = false;
  try {
    stopped = await hooks.stopEngine();
  } catch (err) {
    logger.error(`engine stop before install failed: ${errorText(err)}`);
  }
  if (!stopped) {
    dispatch({ type: 'install-failed', message: 'local engine did not stop; nothing was installed' });
    await recoverEngine();
    await ask.box({
      type: 'warning',
      title: 'Nova update not installed',
      message: 'Nova could not confirm its local engine stopped, so it did not install the update.',
      detail: 'The engine is restarting. Try Help > Restart to Update again.',
      buttons: ['OK'],
      noLink: true,
    });
    return;
  }
  logger.info(`installing ${displayTag(state.version)} at the operator's request`);
  try {
    // Silent NSIS install into the existing location, then relaunch the new
    // version, which starts its own matching engine. Settings live in userData.
    updater.quitAndInstall(true, true);
  } catch (err) {
    dispatch({ type: 'install-failed', message: errorText(err) });
    await recoverEngine();
  }
}

/** @param {'launch' | 'manual' | 'recheck'} origin */
async function checkNow(origin) {
  if (!updater) return;
  const manual = origin === 'manual';
  const action = manual ? manualCheckAction(state, gate) : shouldAutoCheck(state, gate) ? 'check' : 'skip';
  if (action === 'prompt' || action === 'offer') {
    // Asked from the menu: raise the notice again, even after Later.
    dispatch({ type: 'reoffer' });
    await offer();
    return;
  }
  if (action !== 'check') return;
  manualPending = manual;
  checkOrigin = origin;
  lastCheckAt = Date.now();
  if (origin === 'recheck') logger.info('re-checking while the desk stays open');
  let result = null;
  try {
    result = await updater.checkForUpdates();
  } catch (err) {
    // electron-updater also emits 'error', which is what the menu shows.
    logger.warn(`check failed: ${errorText(err)}`);
    return;
  }
  if (!result?.isUpdateAvailable) return;
  pendingInfo = result.updateInfo;
  manualPending = false; // the notice is the answer
  if (hasConsent(state)) {
    logger.info(`resuming the download of ${displayTag(state.version)}`);
    await startDownload();
    return;
  }
  if (manual) dispatch({ type: 'reoffer' });
  if (shouldOfferNow(state, { origin, now: Date.now() })) await offer();
  else if (needsOffer(state)) logger.info(`${displayTag(state.version)} found; the notice waits until trading hours end`);
}

async function fetchUpdate(info) {
  try {
    await downloadRelease({
      updater,
      info,
      fetch: (url, init) => net.fetch(url, init),
      logger,
      onProgress: (percent) => dispatch({ type: 'progress', percent }),
      onRetry: ({ attempt }) => dispatch({ type: 'retrying', attempt }),
    });
  } catch (err) {
    logger.error(`download failed: ${errorText(err)}`);
    dispatch({ type: 'error', message: errorText(err) });
    void reportManualResult();
  }
}

function wireEvents(instance) {
  instance.on('checking-for-update', () => dispatch({ type: 'checking' }));
  instance.on('update-available', (info) => dispatch({ type: 'available', version: info?.version }));
  instance.on('update-not-available', () => {
    dispatch({ type: 'not-available' });
    void reportManualResult();
  });
  instance.on('download-progress', (p) => dispatch({ type: 'progress', percent: p?.percent }));
  instance.on('update-downloaded', (info) => {
    manualPending = false;
    dispatch({ type: 'downloaded', version: info?.version });
    // The operator chose Update: the notice turns to Restart to update, or the dialog asks.
    if (bridge.hasListener()) ask.attention();
    else void promptRestart();
  });
  instance.on('error', (err) => {
    const wasInstalling = state.phase === 'installing';
    logger.error(`update error: ${errorText(err)}`);
    dispatch({ type: 'error', message: errorText(err) });
    if (wasInstalling) void recoverEngine();
    void reportManualResult();
  });
}

/** The operator's answers from the desk's notice and What's new card. */
function wireBridge(instance) {
  instance.on('download', () => startDownload());
  instance.on('later', () => later());
  instance.on('restart', () => restartToUpdate());
  instance.on('whats-new-close', () => whatsNew?.close());
  instance.on('open-link', async ({ url }) => {
    if (!isReleaseLink(url)) throw new Error(`not a Nova release link: ${url}`);
    await shell.openExternal(url);
  });
}

async function loadUpdater() {
  const mod = await import('electron-updater');
  const NsisUpdater = mod.NsisUpdater ?? mod.default?.NsisUpdater;
  if (typeof NsisUpdater !== 'function') throw new Error('electron-updater has no NsisUpdater');
  // Reads resources/app-update.yml (GitHub provider, written by electron-builder).
  const instance = new NsisUpdater();
  instance.logger = logger;
  // Nothing downloads until the operator picks Update; fetchUpdate() does it then.
  instance.autoDownload = false;
  instance.autoInstallOnAppQuit = false;
  instance.autoRunAppAfterInstall = true;
  instance.allowPrerelease = false;
  instance.allowDowngrade = false;
  return instance;
}

/**
 * Start once, after the main window exists. Never throws.
 * @param {{ getWindow: () => any, envPath: () => string,
 *   stopEngine: () => Promise<boolean>, restartEngine: () => Promise<void> }} deps
 */
export async function startAutoUpdate(deps) {
  try {
    await startUnguarded(deps);
  } catch (err) {
    logger.error(`in-app updates failed to start: ${errorText(err)}`);
  }
}

async function startUnguarded(deps) {
  hooks = { ...hooks, ...deps };
  // Always answers the window, so a dev checkout's page reads an empty view.
  bridge = createUpdateBridge({ ipcMain, getWindow: liveWindow, logger });
  wireBridge(bridge);
  const userData = () => appDir('userData');
  const notesSource = createNotesSource({ fetch: (url, init) => net.fetch(url, init), dir: userData, logger });
  const installedTag = () => currentTag;
  ask = createUpdateAsk({ bridge, notesSource, getWindow: liveWindow, getState: () => state, installedTag, logger });
  gate = updateGate({ isPackaged: app.isPackaged, platform: process.platform, setting: readSetting() });
  if (!gate.updater) {
    logger.info(`in-app updates off: ${gate.reason}`);
    return;
  }
  currentTag = displayTag(app.getVersion());
  bridge.set('installed', currentTag);
  whatsNew = createWhatsNew({ bridge, notesSource, dir: userData, installedTag: currentTag, logger, showDialog: ask.box });
  void whatsNew.start().catch((err) => logger.warn(`What's new failed: ${errorText(err)}`));
  try {
    updater = await loadUpdater();
    wireEvents(updater);
  } catch (err) {
    updater = null;
    logger.error(`in-app updates unavailable: ${errorText(err)}`);
    return;
  }
  renderMenu();
  if (!gate.automatic) {
    logger.info(`automatic update check off: ${gate.reason}`);
    return;
  }
  const timer = setTimeout(() => void checkNow('launch'), UPDATE_FIRST_CHECK_DELAY_MS);
  timer.unref?.();
  const clock = setInterval(tick, UPDATE_RECHECK_TICK_MS);
  clock.unref?.();
}

/** The open desk's clock: a re-check that is due, or a re-check's held notice once trading hours end. */
function tick() {
  const now = Date.now();
  if (shouldRecheck(state, gate, { now, lastCheckAt })) void checkNow('recheck');
  else if (shouldOfferNow(state, { origin: checkOrigin, now })) void offer();
}
