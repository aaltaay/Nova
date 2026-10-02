/** Public hot list API -- cross-feature imports must use this barrel (ADR 005). */
export { hotListActions, listedOn, resetHotListForTests, useHotList, type HotListState } from './hotListStore';
export { normalizeHotList } from './hotListApi';
export { HOT_LIST_AUTO_CHOICES } from './constants';
export type { HotEntry, HotListView, HotSide } from './types';
