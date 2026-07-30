/**
 * Scanner left rail (Webull-style) -- data-driven from the module registry.
 * Horizontal tab bar retired; Account/Settings stay on GlobalAppBar.
 */
import { scannerNavIcon, formatScannerNavCount } from '../scanner/scannerNavIcons';
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

/** @deprecated Prefer ScannerSideNav name in new code -- same component. */
export function TabNav(props: Props) {
  return <ScannerSideNav {...props} />;
}

export function ScannerSideNav({
  activeTab,
  onTabClick,
  counts,
  visibility,
}: Props) {
  const tabs = listTabModules().filter((m) => visibility[m.id] !== false);

  return (
    <nav
      className="scanner-side-nav"
      aria-label="Scanner views"
      data-active-tab={activeTab}
      data-testid="scanner-side-nav"
    >
      <div className="scanner-side-nav__list">
        {tabs.map((m) => {
          const count = m.countKey ? (counts[m.countKey] ?? 0) : 0;
          const countLabel = formatScannerNavCount(count);
          const active = activeTab === m.id;
          return (
            <button
              key={m.id}
              type="button"
              className={`scanner-side-nav__item${active ? ' is-active' : ''}`}
              data-tab={m.id}
              data-testid={`scanner-nav-${m.id}`}
              aria-current={active ? 'page' : undefined}
              title={m.title}
              onClick={() => onTabClick(m.id as ActiveTab)}
            >
              <span className="scanner-side-nav__icon">
                {scannerNavIcon(m.id)}
                {countLabel ? (
                  <span className="scanner-side-nav__count">{countLabel}</span>
                ) : null}
              </span>
              <span className="scanner-side-nav__label">{m.title}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
