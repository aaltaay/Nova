/**
 * TabNav — data-driven from the module registry (Phase 4).
 * Tab row is scanner tabs only; scan age / data source live in AppHeader.
 */
import {
  listTabModules,
  type ActiveTab,
  type ModuleCountKey,
} from '../workspace/registry';

export type { ActiveTab } from '../workspace/registry';

export type TabCounts = Partial<Record<ModuleCountKey, number>>;

interface Props {
  activeTab: ActiveTab;
  onTabClick: (tab: ActiveTab) => void;
  counts: TabCounts;
  /** Module visibility map (tabs filtered). */
  visibility: Record<string, boolean>;
}

export function TabNav({
  activeTab,
  onTabClick,
  counts,
  visibility,
}: Props) {
  const tabs = listTabModules().filter(m => visibility[m.id] !== false);

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
      </div>
    </div>
  );
}
