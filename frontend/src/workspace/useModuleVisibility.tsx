/**
 * Shared module visibility — Modules menu + panels read the same map.
 * Persisted to localStorage via moduleVisibility helpers.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  isModuleVisible,
  loadModuleVisibility,
  saveModuleVisibility,
  type ModuleVisibilityMap,
} from './moduleVisibility';

type ModuleVisibilityValue = {
  visibility: ModuleVisibilityMap;
  setModuleVisible: (id: string, visible: boolean) => void;
  isVisible: (id: string) => boolean;
};

const ModuleVisibilityContext = createContext<ModuleVisibilityValue | null>(null);

export function ModuleVisibilityProvider({ children }: { children: ReactNode }) {
  const [visibility, setVisibility] = useState<ModuleVisibilityMap>(() =>
    loadModuleVisibility(),
  );

  const setModuleVisible = useCallback((id: string, visible: boolean) => {
    setVisibility(prev => {
      const next = { ...prev, [id]: visible };
      saveModuleVisibility(next);
      return next;
    });
  }, []);

  const isVisible = useCallback(
    (id: string) => isModuleVisible(id, visibility),
    [visibility],
  );

  const value = useMemo(
    () => ({ visibility, setModuleVisible, isVisible }),
    [visibility, setModuleVisible, isVisible],
  );

  return (
    <ModuleVisibilityContext.Provider value={value}>
      {children}
    </ModuleVisibilityContext.Provider>
  );
}

export function useModuleVisibility(): ModuleVisibilityValue {
  const ctx = useContext(ModuleVisibilityContext);
  if (!ctx) {
    throw new Error('useModuleVisibility must be used within ModuleVisibilityProvider');
  }
  return ctx;
}
