/**
 * Public watch list API -- cross-feature imports must use this barrel (ADR 005).
 * Kept light on purpose: every ticker list imports it, so nothing here may pull
 * the HOD Momo or setups features in. The toasts (`WatchListToasts`, which listen
 * to the HOD stream and the setup scanner's board) mount once with the app bar,
 * and the tab loads lazily, both by path.
 */

export {
  addToWatchList,
  getWatchList,
  isWatched,
  removeFromWatchList,
  toggleWatchList,
  useIsWatched,
  useWatchList,
} from './watchListStore';
export {
  WATCH_ACTION_WATCH,
  WATCH_ACTION_WATCH_TITLE,
  WATCH_ACTION_WATCHING,
  WATCH_ACTION_WATCHING_TITLE,
  WATCH_LIST_ADD,
  WATCH_LIST_REMOVE,
  WATCH_LIST_TITLE,
  watchListAddLabel,
  watchListRemoveLabel,
  watchMarkTitle,
} from './watchListConstants';
export { WatchEyeIcon } from './WatchEyeIcon';
export { WatchMark } from './WatchMark';
export type { WatchListBoards } from './types';
