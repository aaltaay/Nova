/**
 * Shared layout store — Modules menu reorder + quote hosts read the same JSON.
 * Persisted via layoutStore helpers (Phase 5); drag-drop writes here (Phase 6).
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
  getSlotOrder,
  loadLayout,
  moveModuleInSlot,
  reorderModulesInSlot,
  resetLayout as resetLayoutPersist,
  saveLayout,
  type LayoutSlotId,
  type WorkspaceLayout,
} from './layoutStore';

type LayoutStoreValue = {
  layout: WorkspaceLayout;
  getOrder: (slot: LayoutSlotId) => string[];
  moveModule: (slot: LayoutSlotId, moduleId: string, direction: 'up' | 'down') => void;
  reorderModules: (slot: LayoutSlotId, activeId: string, overId: string) => void;
  resetToDefault: () => void;
};

const LayoutStoreContext = createContext<LayoutStoreValue | null>(null);

export function LayoutStoreProvider({ children }: { children: ReactNode }) {
  const [layout, setLayout] = useState<WorkspaceLayout>(() => loadLayout());

  const getOrder = useCallback(
    (slot: LayoutSlotId) => getSlotOrder(layout, slot),
    [layout],
  );

  const moveModule = useCallback(
    (slot: LayoutSlotId, moduleId: string, direction: 'up' | 'down') => {
      setLayout(prev => {
        const next = moveModuleInSlot(prev, slot, moduleId, direction);
        if (next === prev) return prev;
        saveLayout(next);
        return next;
      });
    },
    [],
  );

  const reorderModules = useCallback(
    (slot: LayoutSlotId, activeId: string, overId: string) => {
      setLayout(prev => {
        const next = reorderModulesInSlot(prev, slot, activeId, overId);
        if (next === prev) return prev;
        saveLayout(next);
        return next;
      });
    },
    [],
  );

  const resetToDefault = useCallback(() => {
    const next = resetLayoutPersist();
    setLayout(next);
  }, []);

  const value = useMemo(
    () => ({ layout, getOrder, moveModule, reorderModules, resetToDefault }),
    [layout, getOrder, moveModule, reorderModules, resetToDefault],
  );

  return (
    <LayoutStoreContext.Provider value={value}>{children}</LayoutStoreContext.Provider>
  );
}

export function useLayoutStore(): LayoutStoreValue {
  const ctx = useContext(LayoutStoreContext);
  if (!ctx) {
    throw new Error('useLayoutStore must be used within LayoutStoreProvider');
  }
  return ctx;
}
