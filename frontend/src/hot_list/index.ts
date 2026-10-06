/** Public hot list API -- cross-feature imports must use this barrel (ADR 005). */
export {
  getHotListState,
  hotListActions,
  howListed,
  listedOn,
  resetHotListForTests,
  subscribeHotList,
  useHotList,
  type HotListState,
} from './hotListStore';
export { normalizeHotList } from './hotListApi';
export { HOT_LIST_AUTO_CHOICES } from './constants';
export type { HotEntry, HotHow, HotListView } from './types';
