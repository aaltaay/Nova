/** Public Stock View (Trader) feature API -- cross-feature imports must use this barrel (ADR 005). */

export { EstChip } from './EstChip';
export { requestStockViewDock } from './requestDockSurface';
export {
  EMPTY_TRADER_TABS,
  TRADER_DRAFT_SYMBOL,
  activateTab,
  addDraftTab,
  addTab,
  capLive,
  closeTab,
  isTabLive,
  parseTraderTabs,
  pinTab,
  releaseOldestLive,
  renameTab,
  serializeTraderTabs,
  unpinTab,
  type TraderTabsState,
} from './traderTabsState';
export { rankUnknownWhy, scannerListRows, type RankListId } from './quoteRank';
