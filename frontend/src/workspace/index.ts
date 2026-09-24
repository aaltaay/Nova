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
export type { NovaModule } from './registry';
