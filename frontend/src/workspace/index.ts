/** Public workspace API — cross-feature imports must use this barrel (ADR 005). */

export {
  useWorkspace,
  WorkspaceProvider,
  type WorkspaceValue,
} from './WorkspaceContext';
export {
  useModuleVisibility,
  ModuleVisibilityProvider,
} from './useModuleVisibility';
export { useLayoutStore, LayoutStoreProvider } from './useLayoutStore';
