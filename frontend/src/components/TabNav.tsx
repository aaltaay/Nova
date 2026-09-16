/**
 * Scanner left rail (Webull-style) -- data-driven from the module registry.
 * Horizontal tab bar retired; Account/Settings stay on GlobalAppBar.
 * HOD Momo / Running Up focus the AppShell dock (not a full-page tab body).
 */
import { AdviseRailButton } from '../advise/AdviseRailButton';
import { scannerNavIcon, formatScannerNavCount } from '../scanner/scannerNavIcons';
import {
  listTabModules,
  type ActiveTab,
  type ModuleCountKey,
} from '../workspace/registry';

export type { ActiveTab } from '../workspace/registry';

export type TabCounts = Partial<Record<ModuleCountKey, number>>;

interface Props {
  /** Main-column tab (never hod_momo / running_up after dock migration). */
  activeTab: ActiveTab;
  /**
   * Which rail item shows as active. When focusing the HOD dock, this is
   * `hod_momo` / `running_up` while `activeTab` stays on the last scanner table.
   */
  railHighlight?: ActiveTab;
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
  railHighlight,
  onTabClick,
  counts,
  visibility,
}: Props) {
  const tabs = listTabModules().filter((m) => visibility[m.id] !== false);
  const highlight = railHighlight ?? activeTab;

  return (
    <nav
      className="scanner-side-nav"
      aria-label="Scanner views"
      data-active-tab={activeTab}
      data-rail-highlight={highlight}
      data-testid="scanner-side-nav"
    >
      <div className="scanner-side-nav__list">
        {tabs.map((m) => {
          const count = m.countKey ? (counts[m.countKey] ?? 0) : 0;
          const countLabel = formatScannerNavCount(count);
          const active = highlight === m.id;
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
      <div className="scanner-side-nav__footer">
        <AdviseRailButton />
      </div>
    </nav>
  );
}
