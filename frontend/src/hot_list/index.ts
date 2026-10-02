/** Public hot list API -- cross-feature imports must use this barrel (ADR 005). */
export {
  getHotListState,
  hotListActions,
  listedOn,
  resetHotListForTests,
  subscribeHotList,
  useHotList,
  type HotListState,
} from './hotListStore';
export { normalizeHotList } from './hotListApi';
export { HOT_LIST_AUTO_CHOICES } from './constants';
export type { HotEntry, HotListView, HotSide } from './types';
