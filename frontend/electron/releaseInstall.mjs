/**
 * Installing the release the operator chose (#347), at their Restart to update.
 *
 * The "Updating Nova" window goes up first (updateSplash.mjs) -- from the click
 * until the new version's window nothing of Nova is on screen but it -- then the
 * local engine stops and electron-updater runs the silent installer, which ends
 * Nova and reopens the new version. An install that cannot go ahead (the engine
 * would not stop, the installer would not start, electron-updater reported an
 * error while installing) takes the window down and restarts the engine; the
 * downloaded installer stays offered.
 */
import path from 'node:path';
import { UPDATE_LOG_FILE } from './updateLog.mjs';
import { displayTag, errorText } from './updatePolicy.mjs';
import { showUpdateSplash } from './updateSplash.mjs';

/**
 * @param {{ getUpdater: () => any, getState: () => { phase: string, version: string },
 *   dispatch: (event: object) => void, stopEngine: () => Promise<boolean>,
 *   restartEngine: () => Promise<void>, box: (options: object) => Promise<unknown>,
 *   logsDir: () => string, logger: { info: Function, error: Function } }} deps
 */
export function createReleaseInstaller({ getUpdater, getState, dispatch, stopEngine, restartEngine, box, logsDir, logger }) {
  /** The "Updating Nova" window while an install runs, or null. */
  let splash = null;

  /** The window closes itself when the new version's window is up; this is for an install called off. */
  function closeSplash() {
    splash?.close();
    splash = null;
  }

  /** Called off: take the window down and bring the engine back. */
  async function recover() {
    closeSplash();
    try {
      await restartEngine();
    } catch (err) {
      logger.error(`engine restart after a failed install: ${errorText(err)}`);
    }
  }

  async function install() {
    const updater = getUpdater();
    if (!updater || getState().phase !== 'ready') return;
    dispatch({ type: 'installing' });
    const { version } = getState();
    const logs = logsDir();
    splash = showUpdateSplash({
      version: displayTag(version),
      processName: path.basename(process.execPath, '.exe'),
      logPath: logs ? path.join(logs, UPDATE_LOG_FILE) : '',
      logger,
    });
    let stopped = false;
    try {
      stopped = await stopEngine();
    } catch (err) {
      logger.error(`engine stop before install failed: ${errorText(err)}`);
    }
    if (!stopped) {
      dispatch({ type: 'install-failed', message: 'local engine did not stop; nothing was installed' });
      await recover();
      await box({
        type: 'warning',
        title: 'Nova update not installed',
        message: 'Nova could not confirm its local engine stopped, so it did not install the update.',
        detail: 'The engine is restarting. Try Help > Restart to Update again.',
        buttons: ['OK'],
        noLink: true,
      });
      return;
    }
    logger.info(`installing ${displayTag(version)} at the operator's request`);
    try {
      // Silent NSIS install into the existing location, then relaunch the new
      // version, which starts its own matching engine. Settings live in userData.
      updater.quitAndInstall(true, true);
    } catch (err) {
      dispatch({ type: 'install-failed', message: errorText(err) });
      await recover();
    }
  }

  return { install, recover };
}
