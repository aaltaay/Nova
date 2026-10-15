/**
 * In-app updates (#347): electron-updater reading this repo's GitHub Releases.
 *
 * A check that finds a newer release tells the operator, with that release's
 * notes, in a notice on the desk: Update / Later (operator ask, 2026-09-23).
 * Update downloads the newest release, checking again when the offer is old
 * (newestRelease.mjs), and Restart to update installs it. Since 2026-10-14 the
 * desk also checks the moment GitHub's release ping arrives (releasePing.mjs),
 * and a found release downloads and installs by itself once nothing is at stake
 * (autoInstall.mjs) unless NOVA_UPDATE_AUTO_INSTALL is off.
 * autoInstallOnAppQuit is off, the re-check runs every two hours while the desk
 * stays open (never in weekday trading hours), and a failed check or download
 * only changes the Help menu. After an update, the first launch shows
 * What's new (whatsNew.mjs). Decisions live in updatePolicy.mjs, words in
 * updateCopy.mjs, reaching the operator (notice, Help menu, dialogs) in
 * updateAsk.mjs, the renderer link in updateBridge.mjs, the release still being
 * built that Help > Check for Updates names in releaseBuild.mjs; this file is
 * the wiring around electron-updater.
 *
 * maintainer: one-concern the one electron-updater instance and the check, offer and download state every path shares -- one check at a time
 *
 * electron-updater checks and installs; the installer itself is fetched in
 * resumable chunks (releaseDownload.mjs) and handed back through electron-updater's
 * cache, because its own one-shot download never finished on a lossy link.
 * Every line of this is also written to update.log (updateLog.mjs). Installing
 * -- the "Updating Nova" window, the engine stop, the silent installer -- is
 * releaseInstall.mjs.
 *
 * electron-updater loads lazily and only in a packaged Windows build, so a dev
 * checkout never loads it. Every failure here is logged and swallowed -- the desk
 * keeps running on the version it has.
 */
import fs from 'node:fs';
import { app, ipcMain, net, powerMonitor, shell } from 'electron';
import { isOlderTag } from './appTitle.mjs';
import { createAutoInstall } from './autoInstall.mjs';
import { readEnvValue } from './envMerge.mjs';
import { downloadRelease } from './releaseDownload.mjs';
import { createReleaseInstaller } from './releaseInstall.mjs';
import { createIssueRequest, isIssueLink } from './issueLinks.mjs';
import { createNewestRelease } from './newestRelease.mjs';
import { createReleaseBuild } from './releaseBuild.mjs';
import { isReleaseLink, notesText } from './releaseNotes.mjs';
import { createNotesSource } from './releaseNotesSource.mjs';
import { createReleasePing } from './releasePing.mjs';
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
  UPDATE_AUTO_INSTALL_ENV,
  UPDATE_AUTO_TICK_MS,
  UPDATE_CHECK_ENV,
  UPDATE_FIRST_CHECK_DELAY_MS,
  UPDATE_PING_MIN_GAP_MS,
  UPDATE_RECHECK_TICK_MS,
  displayTag,
  errorText,
  hasConsent,
  manualCheckAction,
  needsOffer,
  offerIsStale,
  reduceUpdateState,
  resolveUpdateSetting,
  shouldAutoCheck,
  shouldOfferNow,
  shouldPingCheck,
  shouldRecheck,
  taskbarProgress,
  updateCheckSetting,
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
let checkRunning = false;
let currentTag = '';
let bridge = null;
let ask = null;
let whatsNew = null;
let installer = null;
let requestIssueForm = null;
// The release on offer: electron-updater's info from the check that found it.
let pendingInfo = null;
// NOVA_UPDATE_AUTO_INSTALL: a found release downloads and installs by itself once nothing is at stake.
let autoInstallOn = false;
let auto = null;
// The download under way was Nova's own (autoInstall.mjs): its end asks nothing -- it installs by itself.
let downloadByItself = false;
// GitHub's release ping (releasePing.mjs): when it last caused a check, and the check a ping inside the gap waits for.
let lastPingCheckAt = 0;
let pingTimer = null;
const newest = createNewestRelease({ getUpdater: () => updater, logger });
const builds = createReleaseBuild({ fetch: (url, init) => net.fetch(url, init), logger });
let hooks = {
  getWindow: () => null,
  envPath: () => '',
  stopEngine: async () => true,
  restartEngine: async () => {},
  // The backend's sync (engineSync.mjs), once the desk attached it; null for a desk that has none.
  engine: () => null,
  // The backend follows the release being installed; false: the operator waits.
  prepareInstall: (tag, ui) => hooks.engine()?.prepareForDesk(tag, ui) ?? Promise.resolve(true),
  // ...and restarts onto it while the installer runs (engineSync.handOffForInstall).
  handOffEngine: () => hooks.engine()?.handOffForInstall() ?? Promise.resolve(),
  // What holds an automatic install (engineFollow.autoRestartHolds); null reads as a backend that did not answer.
  autoHolds: () => hooks.engine()?.autoHolds() ?? Promise.resolve(null),
};

/** A desk setting: the process env wins, else the desk .env. */
function readSetting(name) {
  let fileValue = '';
  const envPath = hooks.envPath();
  try {
    if (envPath && fs.existsSync(envPath)) {
      fileValue = readEnvValue(fs.readFileSync(envPath, 'utf8'), name);
    }
  } catch (err) {
    logger.warn(`cannot read ${name} from ${envPath}: ${errorText(err)}`);
  }
  return resolveUpdateSetting({ processValue: process.env[name], fileValue });
}

/** Windows' time since the last keyboard or mouse input. */
function idleMs() {
  return powerMonitor.getSystemIdleTime() * 1000;
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
    'file-issue': () => requestIssueForm?.(),
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
  const settled = state;
  if (!manualCheckResult(settled, currentTag)) return;
  manualPending = false;
  // Nothing newer is released: a newer one still being built is named beside that (releaseBuild.mjs).
  const building = settled.phase === 'current' ? await builds.find(currentTag) : null;
  const result = manualCheckResult(settled, currentTag, { building, now: Date.now() });
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

/** Later -- or Hide, its label while downloading, which only hides: Nova still installs it by itself. */
function later() {
  if (!state.version) return;
  if (state.phase === 'downloading') {
    logger.info(`${displayTag(state.version)} download hidden by operator`);
    dispatch({ type: 'hidden', version: state.version });
    return;
  }
  logger.info(`${displayTag(state.version)} postponed by operator`);
  dispatch({ type: 'dismissed', version: state.version });
}

async function promptRestart() {
  if (isRestartChoice(await ask.ask(restartPrompt(state.version)))) await restartToUpdate();
  else later();
}

const BY_ITSELF = 'by itself';

/**
 * Update (or Resume): download the newest release. A stopped download is re-checked first.
 * `how` says in update.log who asked: the operator, or Nova BY_ITSELF (autoInstall.mjs).
 */
async function startDownload(how = "at the operator's request") {
  if (!updater || newest.isChecking()) return;
  if (state.phase === 'failed' && state.failedStage === 'download') {
    // The check finds the same release and resumes it: the operator already chose it.
    await checkNow('manual');
    return;
  }
  if (state.phase !== 'available' || !pendingInfo) return;
  const onOffer = state.version;
  const now = Date.now();
  if (offerIsStale({ now, lastCheckAt })) {
    // The notice may have waited for hours; take what is newest now (newestRelease.mjs).
    lastCheckAt = now;
    pendingInfo = await newest.check(pendingInfo);
    if (!pendingInfo) {
      dispatch({ type: 'not-available' });
      return;
    }
  }
  if (state.phase !== 'available') return;
  dispatch({ type: 'download', version: pendingInfo.version });
  // A newer release than the notice named: its notes run through the new one.
  if (state.version !== onOffer) void ask.notesFor(displayTag(state.version));
  downloadByItself = how === BY_ITSELF;
  logger.info(`downloading ${displayTag(state.version)} ${how}`);
  await fetchUpdate(pendingInfo);
}

async function restartToUpdate() {
  await installer?.install();
}

/** Nova may download and install by itself: automatic checks on, and NOVA_UPDATE_AUTO_INSTALL not off. */
function autoEnabled() {
  return Boolean(updater && gate.automatic && autoInstallOn);
}

/** How a check chooses: the operator's asks anything not busy; a ping, one newer release; the rest, the startup rule. */
function checkAction(origin) {
  if (origin === 'manual') return manualCheckAction(state, gate);
  if (origin === 'ping') return shouldPingCheck(state, gate) ? 'check' : 'skip';
  return shouldAutoCheck(state, gate) ? 'check' : 'skip';
}

/**
 * GitHub's release ping named `tag`: check now when it is newer than this desk and than the
 * release in hand, at most once per UPDATE_PING_MIN_GAP_MS (a ping inside the gap checks after it).
 */
function onReleasePing(tag) {
  if (!isOlderTag(currentTag, tag)) return;
  if (state.version && !isOlderTag(displayTag(state.version), tag)) return;
  const wait = lastPingCheckAt + UPDATE_PING_MIN_GAP_MS - Date.now();
  const run = () => {
    pingTimer = null;
    lastPingCheckAt = Date.now();
    logger.info(`GitHub says ${tag} is out; checking now`);
    void checkNow('ping');
  };
  if (wait <= 0) run();
  else if (!pingTimer) {
    pingTimer = setTimeout(run, wait);
    pingTimer.unref?.();
  }
}

/**
 * One check at a time. Help > Check for Updates asks GitHub even with a release
 * on offer or downloaded, and what it finds raises the notice again.
 * @param {'launch' | 'manual' | 'recheck' | 'ping'} origin
 */
async function checkNow(origin) {
  if (!updater) return;
  const manual = origin === 'manual';
  if (checkRunning) {
    // Asked while a check runs: that check's answer is the operator's.
    if (manual) {
      manualPending = true;
      checkOrigin = origin;
    }
    return;
  }
  // Update's own check (newestRelease.mjs) is running: the download it leads to is the answer.
  if (newest.isChecking()) return;
  if (checkAction(origin) !== 'check') return;
  manualPending = manual;
  checkOrigin = origin;
  lastCheckAt = Date.now();
  if (origin === 'recheck') logger.info('re-checking while the desk stays open');
  let result = null;
  checkRunning = true;
  try {
    result = await updater.checkForUpdates();
  } catch (err) {
    // electron-updater also emits 'error', which is what the menu shows.
    logger.warn(`check failed: ${errorText(err)}`);
    return;
  } finally {
    checkRunning = false;
  }
  if (!result?.isUpdateAvailable) return;
  pendingInfo = result.updateInfo;
  manualPending = false; // the notice is the answer
  if (hasConsent(state)) {
    logger.info(`resuming the download of ${displayTag(state.version)}`);
    await startDownload();
    return;
  }
  // Asked from the menu: raise the notice again, even after Later.
  if (checkOrigin === 'manual') dispatch({ type: 'reoffer' });
  // Nothing at stake: it downloads now, and the notice follows the download.
  if (autoEnabled() && (await auto.step())) return;
  if (shouldOfferNow(state, { origin: checkOrigin, now: Date.now() })) await offer();
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
  // The check an Update click runs answers through its result (newestRelease.mjs), not its events.
  const on = (name, handle) => instance.on(name, (...args) => {
    if (!newest.isChecking()) handle(...args);
  });
  on('checking-for-update', () => dispatch({ type: 'checking' }));
  on('update-available', (info) => dispatch({ type: 'available', version: info?.version }));
  on('update-not-available', () => {
    dispatch({ type: 'not-available' });
    void reportManualResult();
  });
  instance.on('download-progress', (p) => dispatch({ type: 'progress', percent: p?.percent }));
  instance.on('update-downloaded', (info) => {
    manualPending = false;
    dispatch({ type: 'downloaded', version: info?.version });
    // The notice turns to Restart to update, or the dialog asks -- unless Nova fetched it by itself.
    if (bridge.hasListener()) ask.attention();
    else if (!downloadByItself) void promptRestart();
  });
  on('error', (err) => {
    const wasInstalling = state.phase === 'installing';
    logger.error(`update error: ${errorText(err)}`);
    dispatch({ type: 'error', message: errorText(err) });
    if (wasInstalling) void installer?.recover();
    void reportManualResult();
  });
}

/** The operator's answers from the desk's notice and What's new card. */
function wireBridge(instance) {
  instance.on('download', () => startDownload());
  instance.on('later', () => later());
  instance.on('restart', () => restartToUpdate());
  // The backend notice, for a backend newer than this desk: look for the desk's release now.
  instance.on('check-update', () => checkNow('manual'));
  instance.on('whats-new-close', () => whatsNew?.close());
  instance.on('open-link', async ({ url }) => {
    // Release notes' links, and the issue form's: the filed issue, its dump, GitHub's page.
    if (!isReleaseLink(url) && !isIssueLink(url)) throw new Error(`not a Nova release or issue link: ${url}`);
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
 *   stopEngine: () => Promise<boolean>, restartEngine: () => Promise<void>,
 *   prepareInstall?: (tag: string, ui: { box: Function }) => Promise<boolean>,
 *   handOffEngine?: () => Promise<void>,
 *   onBridge?: (bridge: object, logger: object) => void }} deps
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
  hooks.onBridge?.(bridge, logger); // the backend follows the desk's release (engineSync.mjs)
  requestIssueForm = createIssueRequest({
    bridge,
    getWindow: liveWindow,
    openExternal: (url) => shell.openExternal(url),
    logger,
  });
  const userData = () => appDir('userData');
  const notesSource = createNotesSource({ fetch: (url, init) => net.fetch(url, init), dir: userData, logger });
  const installedTag = () => currentTag;
  ask = createUpdateAsk({ bridge, notesSource, getWindow: liveWindow, getState: () => state, installedTag, logger });
  installer = createReleaseInstaller({
    getUpdater: () => updater,
    getState: () => state,
    dispatch,
    prepare: (tag, options) => hooks.prepareInstall(tag, { box: ask.box, ...options }),
    stopEngine: () => hooks.stopEngine(),
    handOff: () => hooks.handOffEngine(),
    restartEngine: () => hooks.restartEngine(),
    box: ask.box,
    logsDir: () => appDir('logs'),
    logger,
  });
  gate = updateGate({ isPackaged: app.isPackaged, platform: process.platform, setting: readSetting(UPDATE_CHECK_ENV) });
  if (!gate.updater) {
    logger.info(`in-app updates off: ${gate.reason}`);
    return;
  }
  autoInstallOn = updateCheckSetting(readSetting(UPDATE_AUTO_INSTALL_ENV));
  auto = createAutoInstall({
    getState: () => state,
    dispatch,
    enabled: autoEnabled,
    holds: () => hooks.autoHolds(),
    idleMs,
    download: () => startDownload(BY_ITSELF),
    install: () => installer.install({ automatic: true }),
    logger,
  });
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
  // GitHub cannot call the desk; the desk keeps a line open to the topic Desktop pack posts to.
  createReleasePing({ fetch: (url, init) => net.fetch(url, init), onRelease: onReleasePing, logger }).start();
  logger.info(autoInstallOn
    ? 'a newer release downloads and installs by itself once nothing is at stake'
    : `${UPDATE_AUTO_INSTALL_ENV} is off: a newer release waits for Update and Restart to update`);
  if (!autoInstallOn) return;
  const autoClock = setInterval(() => void auto.step(), UPDATE_AUTO_TICK_MS);
  autoClock.unref?.();
}

/** The open desk's clock: a re-check that is due, or a re-check's held notice once trading hours end. */
function tick() {
  const now = Date.now();
  if (shouldRecheck(state, gate, { now, lastCheckAt })) void checkNow('recheck');
  else if (shouldOfferNow(state, { origin: checkOrigin, now })) void offer();
}
