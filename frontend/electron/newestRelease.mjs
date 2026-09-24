/**
 * What Update downloads: the newest release, not the one the notice first named.
 *
 * A notice can wait out a trading morning while releases keep shipping. On
 * 2026-09-24 v1004 was found at 10:42 ET, v1005 shipped at 11:30, and Update at
 * 13:20 downloaded v1004, because re-checks hold in trading hours and Update
 * took the old answer. So autoUpdate.mjs asks GitHub again at an Update click on
 * an offer older than UPDATE_OFFER_FRESH_MS (updatePolicy.mjs), through here.
 *
 * That check answers through its result only: while it runs, isChecking() is
 * true and autoUpdate.mjs keeps its electron-updater events out of the state, so
 * the notice never blinks through "checking" or "check failed". A failed check
 * downloads the release on offer, as before. electron-updater keeps the info of
 * its last successful check, so its download stays the release returned here.
 */
import { displayTag, errorText } from './updatePolicy.mjs';

/** @param {{ getUpdater: () => any, logger: { info: Function, warn: Function } }} deps */
export function createNewestRelease({ getUpdater, logger }) {
  let checking = false;

  /**
   * @param {any} info electron-updater's info for the release on offer
   * @returns {Promise<any>} the newest release's info; `info` itself when the
   *   check fails; null when GitHub has nothing newer than this desk any more
   */
  async function check(info) {
    const onOffer = displayTag(info?.version);
    logger.info(`${onOffer} was found a while ago; checking for a newer release before downloading`);
    checking = true;
    let result = null;
    try {
      result = await getUpdater().checkForUpdates();
    } catch (err) {
      logger.warn(`check before the download failed (${errorText(err)}); downloading ${onOffer}`);
      return info;
    } finally {
      checking = false;
    }
    if (!result) return info;
    if (!result.isUpdateAvailable) {
      logger.info(`GitHub offers nothing newer than this desk any more; ${onOffer} is not downloaded`);
      return null;
    }
    const found = displayTag(result.updateInfo?.version);
    if (found !== onOffer) logger.info(`${found} shipped after ${onOffer} was found; downloading ${found} instead`);
    return result.updateInfo;
  }

  return { check, isChecking: () => checking };
}
