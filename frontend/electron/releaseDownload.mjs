/**
 * Hands a release the operator chose to electron-updater (#347): its installer
 * is fetched the resumable way (updateDownload.mjs) into electron-updater's
 * cache, then electron-updater verifies it; when the resumable download cannot
 * be planned, electron-updater downloads it itself. electron-updater's events
 * say how that ended ('update-downloaded' or 'error'); a resumable download that
 * gives up throws, keeping what arrived for Resume.
 */
import { downloadInstaller, installerTarget } from './updateDownload.mjs';
import { errorText } from './updatePolicy.mjs';

/** Where and what to download, exactly as electron-updater would; null if it cannot say. */
async function planDownload(updater, info, logger) {
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

/**
 * @param {{ updater: any, info: any, fetch: (url: string, init?: object) => Promise<Response>,
 *   logger: { warn: Function }, onProgress: (percent: number) => void,
 *   onRetry: (retry: { attempt: number }) => void }} opts
 */
export async function downloadRelease({ updater, info, fetch, logger, onProgress, onRetry }) {
  const plan = await planDownload(updater, info, logger);
  if (!plan) {
    logger.warn('resumable download unavailable; falling back to electron-updater\'s own download');
    // Its failures arrive as 'error' events; only keep the promise from going unhandled.
    await updater.downloadUpdate().catch(() => {});
    return;
  }
  await downloadInstaller({ ...plan, fetch, logger, onProgress, onRetry });
  // electron-updater finds the verified installer in its cache, hashes it again,
  // and emits 'update-downloaded' (or 'error').
  await updater.downloadUpdate().catch(() => {});
}
