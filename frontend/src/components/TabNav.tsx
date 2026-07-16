/**
 * TabNav — data-driven from the module registry (Phase 4).
 * Tab row is tabs-only; scan age / data source live in AppHeader.
 * Modules menu also hosts Phase 5 panel-order controls.
 */
import { useState } from 'react';
import { ModulesMenu } from './ModulesMenu';
import {
  listTabModules,
  type ActiveTab,
  type ModuleCountKey,
} from '../workspace/registry';
import type { LayoutSlotId } from '../workspace/layoutStore';
import { useLayoutStore } from '../workspace/useLayoutStore';

export type { ActiveTab } from '../workspace/registry';

export type TabCounts = Partial<Record<ModuleCountKey, number>>;

interface Props {
  activeTab: ActiveTab;
  onTabClick: (tab: ActiveTab) => void;
  counts: TabCounts;
  /** Module visibility map (tabs filtered; menu toggles all). */
  visibility: Record<string, boolean>;
  onToggleModule: (id: string, visible: boolean) => void;
  modulesMenuOpen: boolean;
  onModulesMenuOpenChange: (open: boolean) => void;
}

export function TabNav({
  activeTab,
  onTabClick,
  counts,
  visibility,
  onToggleModule,
  modulesMenuOpen,
  onModulesMenuOpenChange,
}: Props) {
  const tabs = listTabModules().filter(m => visibility[m.id] !== false);
  const { getOrder, moveModule, reorderModules, resetToDefault } = useLayoutStore();
  const [reorderSlot, setReorderSlot] = useState<LayoutSlotId>('side_panel');

  return (
    <div className="tab-bar" data-active-tab={activeTab}>
      <div className="tab-bar-scroll">
        {tabs.map(m => {
          const count = m.countKey ? counts[m.countKey] ?? 0 : 0;
          return (
            <button
              key={m.id}
              type="button"
              className={activeTab === m.id ? 'tab active' : 'tab'}
              data-tab={m.id}
              onClick={() => onTabClick(m.id as ActiveTab)}
            >
              {m.title}
              {m.badge && <span className="tab-badge-broker">{m.badge}</span>}
              {count > 0 && <span className="tab-count">{count}</span>}
            </button>
          );
        })}
        <ModulesMenu
          visibility={visibility}
          onToggle={onToggleModule}
          panelOrder={getOrder(reorderSlot)}
          reorderSlot={reorderSlot}
          onReorderSlotChange={setReorderSlot}
          onMove={(id, dir) => moveModule(reorderSlot, id, dir)}
          onReorder={(activeId, overId) => reorderModules(reorderSlot, activeId, overId)}
          onResetLayout={resetToDefault}
          open={modulesMenuOpen}
          onOpenChange={onModulesMenuOpenChange}
        />
      </div>
    </div>
  );
}
