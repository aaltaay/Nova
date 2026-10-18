/** Public workspace API — cross-feature imports must use this barrel (ADR 005). */

export {
  useWorkspace,
  WorkspaceProvider,
  WorkspaceValueProvider,
  type TraderMoveLocks,
  type WorkspaceValue,
} from './WorkspaceContext';
export {
  useModuleVisibility,
  ModuleVisibilityProvider,
} from './useModuleVisibility';
export { useLayoutStore, LayoutStoreProvider } from './useLayoutStore';
export {
  consumeFocusListRequest,
  requestFocusList,
  subscribeFocusListRequest,
} from './focusListRequest';
export { DEFAULT_ACTIVE_TAB } from './defaultTab';
export { requestScannerTab, setNavPage, useNavRailSnapshot } from './navRailStore';
export {
  isTabModuleId,
  listScannerListModules,
  tabUsesScannerPricePatch,
  type ActiveTab,
  type NovaModule,
} from './registry';
export { declaresScannerL1 } from './scannerTabs';
export {
  allowTraderTabDrop,
  canExtractFromDesk,
  isForeignTabDrag,
  startTraderTabDrag,
  takeForeignTraderTabDrop,
  type TraderTabDragPayload,
} from './traderDesk';
