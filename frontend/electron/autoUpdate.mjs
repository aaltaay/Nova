/**
 * In-app updates (#347): electron-updater reading this repo's GitHub Releases.
 *
 * Downloads a newer installer in the background, then offers "Restart to update"
 * / "Later". Installing is always an operator click: autoInstallOnAppQuit is off,
 * the only timer re-checks (every two hours while the desk stays open, never in
 * weekday trading hours), and a failed check or download only changes the Help menu.
 * Decisions live in updatePolicy.mjs; this file is the Electron wiring.
 *
 * electron-updater checks and installs; the installer itself is fetched by
 * updateDownload.mjs in resumable chunks and handed back through electron-updater's
 * cache, because its own one-shot download never finished on a lossy link.
 * Every line of this is also written to update.log (updateLog.mjs).
 *
 * electron-updater loads lazily and only in a packaged Windows build, so a dev
 * checkout never loads it. Every failure here is logged and swallowed -- the desk
 * keeps running on the version it has.
 */
import fs from 'node:fs';
import { app, dialog, Menu, net } from 'electron';
import { readEnvValue } from './envMerge.mjs';
import { downloadInstaller, installerTarget } from './updateDownload.mjs';
import { createUpdateLogger } from './updateLog.mjs';
import {
  INITIAL_UPDATE_STATE,
  UPDATE_CHECK_ENV,
  UPDATE_FIRST_CHECK_DELAY_MS,
  UPDATE_RECHECK_TICK_MS,
  displayTag,
  errorText,
  isRestartChoice,
  manualCheckAction,
  manualCheckResult,
  reduceUpdateState,
  resolveUpdateSetting,
  restartPrompt,
  shouldAutoCheck,
  shouldPromptNow,
  shouldPromptRestart,
  shouldRecheck,
  taskbarProgress,
  updateGate,
  updateMenuItems,
} from './updatePolicy.mjs';

function logsDir() {
  try {
    return app.getPath('logs');
  } catch {
    return '';
  }
}

const logger = createUpdateLogger({ prefix: '[nova-update]', dir: logsDir });

let updater = null;
let gate = { updater: false, automatic: false, reason: 'not started' };
let state = INITIAL_UPDATE_STATE;
let manualPending = false;
// Which check is running ('launch' | 'manual' | 'recheck') and when the last one began.
let checkOrigin = 'launch';
let lastCheckAt = 0;
let currentTag = '';
let lastMenuKey = '';
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
  const rows = updateMenuItems(state, { currentTag, automatic: gate.automatic });
  const key = JSON.stringify(rows);
  if (key === lastMenuKey) return;
  lastMenuKey = key;
  const clicks = { restart: () => void restartToUpdate(), check: () => void checkNow('manual') };
  const submenu = rows.map((row) => ({
    label: row.label,
    enabled: Boolean(row.action),
    click: clicks[row.action],
  }));
  // Same roles as Electron's default Windows menu; only Help gains the update rows.
  const template = [
    { role: 'fileMenu' },
    { role: 'editMenu' },
    { role: 'viewMenu' },
    { role: 'windowMenu' },
    { role: 'help', submenu },
  ];
  try {
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  } catch (err) {
    logger.error(`menu update failed: ${errorText(err)}`);
  }
}

function dispatch(event) {
  state = reduceUpdateState(state, event);
  renderMenu();
  const win = liveWindow();
  if (win) win.setProgressBar(taskbarProgress(state));
}

async function showBox(options) {
  try {
    const win = liveWindow();
    return win ? await dialog.showMessageBox(win, options) : await dialog.showMessageBox(options);
  } catch (err) {
    logger.error(`dialog failed: ${errorText(err)}`);
    return { response: -1 };
  }
}

async function reportManualResult() {
  if (!manualPending) return;
  const result = manualCheckResult(state, currentTag);
  if (!result) return;
  manualPending = false;
  await showBox({ title: 'Nova updates', buttons: ['OK'], noLink: true, ...result });
}

async function promptRestart() {
  const version = state.version;
  dispatch({ type: 'prompted', version });
  const win = liveWindow();
  if (win) win.flashFrame(true);
  // No parent window: the prompt never blocks the trading window it sits over.
  let response = -1;
  try {
    ({ response } = await dialog.showMessageBox(restartPrompt(version)));
  } catch (err) {
    logger.error(`restart prompt failed: ${errorText(err)}`);
  }
  if (win && !win.isDestroyed()) win.flashFrame(false);
  if (isRestartChoice(response)) await restartToUpdate();
  else logger.info(`restart to ${displayTag(version)} postponed by operator`);
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
    await showBox({
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
  if (action === 'prompt') {
    await promptRestart();
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
  if (result?.isUpdateAvailable) await fetchUpdate(result.updateInfo);
}

/** Where and what to download, exactly as electron-updater would; null if it cannot say. */
async function planDownload(info) {
  try {
    const provider = updater.updateInfoAndProvider?.provider;
    const target = installerTarget(provider?.resolveFiles(info), info?.version);
    const cacheDir = (await updater.getOrCreateDownloadHelper())?.cacheDir;
    return target && cacheDir ? { target, cacheDir } : null;
  } catch (err) {
    logger.warn(`cannot plan a resumable download: ${errorText(err)}`);
    return null;
  }
}

async function fetchUpdate(info) {
  const plan = await planDownload(info);
  if (!plan) {
    logger.warn('resumable download unavailable; falling back to electron-updater\'s own download');
    // Its failures arrive as 'error' events; only keep the promise from going unhandled.
    await updater.downloadUpdate().catch(() => {});
    return;
  }
  try {
    await downloadInstaller({
      ...plan,
      fetch: (url, init) => net.fetch(url, init),
      logger,
      onProgress: (percent) => dispatch({ type: 'progress', percent }),
      onRetry: ({ attempt }) => dispatch({ type: 'retrying', attempt }),
    });
  } catch (err) {
    logger.error(`download failed: ${errorText(err)}`);
    dispatch({ type: 'error', message: errorText(err) });
    void reportManualResult();
    return;
  }
  // electron-updater finds the verified installer in its cache, hashes it again,
  // and emits 'update-downloaded' (or 'error'), which drive the prompt.
  await updater.downloadUpdate().catch(() => {});
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
    if (shouldPromptNow(state, { origin: checkOrigin, now: Date.now() })) void promptRestart();
    else if (shouldPromptRestart(state)) {
      logger.info(`${displayTag(state.version)} is ready; the prompt waits until trading hours end`);
    }
  });
  instance.on('error', (err) => {
    const wasInstalling = state.phase === 'installing';
    logger.error(`update error: ${errorText(err)}`);
    dispatch({ type: 'error', message: errorText(err) });
    if (wasInstalling) void recoverEngine();
    void reportManualResult();
  });
}

async function loadUpdater() {
  const mod = await import('electron-updater');
  const NsisUpdater = mod.NsisUpdater ?? mod.default?.NsisUpdater;
  if (typeof NsisUpdater !== 'function') throw new Error('electron-updater has no NsisUpdater');
  // Reads resources/app-update.yml (GitHub provider, written by electron-builder).
  const instance = new NsisUpdater();
  instance.logger = logger;
  // fetchUpdate() downloads; electron-updater's one-shot download is only the fallback.
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
  gate = updateGate({ isPackaged: app.isPackaged, platform: process.platform, setting: readSetting() });
  if (!gate.updater) {
    logger.info(`in-app updates off: ${gate.reason}`);
    return;
  }
  currentTag = displayTag(app.getVersion());
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

/** The open desk's clock: a re-check that is due, or a re-check's held prompt once trading hours end. */
function tick() {
  const now = Date.now();
  if (shouldRecheck(state, gate, { now, lastCheckAt })) void checkNow('recheck');
  else if (shouldPromptNow(state, { origin: checkOrigin, now })) void promptRestart();
}
