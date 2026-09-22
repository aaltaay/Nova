/**
 * The one navigation rail (approved UX redesign, first slice): 200 px
 * labelled, 56 px icon-only. The Scanner tree stays open in both widths --
 * collapsed it is a tray of child icons with a hairline between groups
 * (operator ask, 2026-09-22) -- until folded by hand. Shared by every view -- Desk, Trader, Scanner
 * (a foldable tree of the registry's grouped tab modules), Account, Bots,
 * Records, then Advise + Settings + collapse pinned at the foot.
 *
 * Routing: Trader is the workspace's Stock View; Desk / Records / Account are
 * shell pages (navRailStore); Scanner children and Bots are dashboard tabs
 * asked for through the store's latch so the request survives a remount.
 */
import { useCallback, useMemo, useState } from 'react';
import '../styles/navRail.css';
import { AdviseRailButton } from '../advise/AdviseRailButton';
import {
  NAV_RAIL_ARIA_LABEL,
  NAV_RAIL_COLLAPSE_TITLE,
  NAV_RAIL_EXPAND_TITLE,
  NAV_RAIL_FOLD_TITLE,
  NAV_RAIL_GROUP_LABELS,
  NAV_RAIL_LABEL_BOTS,
  NAV_RAIL_LABEL_DESK,
  NAV_RAIL_LABEL_RECORDS,
  NAV_RAIL_LABEL_SCANNER,
  NAV_RAIL_LABEL_SETTINGS,
  NAV_RAIL_LABEL_TRADER,
  NAV_RAIL_RECORDING_MAX,
  NAV_RAIL_TITLE_BOTS,
  NAV_RAIL_TITLE_DESK,
  NAV_RAIL_TITLE_RECORDS,
  NAV_RAIL_TITLE_SCANNER,
  NAV_RAIL_TITLE_SETTINGS,
  NAV_RAIL_TITLE_TRADER,
  NAV_RAIL_STRIP_FOCUS_TITLE,
  NAV_RAIL_UNFOLD_TITLE,
  navRailAlertSymbolsTitle,
  navRailRecordingTitle,
} from '../constantGroups/nav_rail';
import { TRADER_DEFAULT_SYMBOL } from '../constants';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import { formatScannerNavCount, scannerNavIcon } from '../scanner/scannerNavIcons';
import {
  navRailCollapsedDefault,
  requestScannerTab,
  setNavPage,
  useNavRailSnapshot,
} from '../workspace/navRailStore';
import { listScannerNavGroups, type ActiveTab } from '../workspace/registry';
import { isDockTab } from '../workspace/scannerTabs';
import { useModuleVisibility } from '../workspace/useModuleVisibility';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { NavRailAccountItem } from './NavRailAccountItem';
import { navRailIcon, NavRailChevron } from './navRailIcons';
import { NavRailItem } from './NavRailItem';
import { readNavRailPrefs, writeNavRailPrefs, type NavRailPrefs } from './navRailPersist';

export interface NavRailProps {
  /** Trader (Stock View) is showing. */
  traderActive: boolean;
  /** Open Trader for a symbol (workspace openStockView / sample openTrader). */
  onOpenTrader: (symbol: string) => void;
  /** Leave Trader for the dashboard side without closing its tabs. */
  onLeaveTrader: () => void;
  /** Settings drawer; null when no SettingsProvider (sample desk). */
  settings?: { open: boolean; toggle: () => void } | null;
}

function isAccountTab(tab: ActiveTab): boolean {
  return tab === 'trading' || tab === 'reports';
}

export function NavRail({ traderActive, onOpenTrader, onLeaveTrader, settings }: NavRailProps) {
  const { page, scanner } = useNavRailSnapshot();
  const { selectedSymbol } = useWorkspace();
  const { visibility } = useModuleVisibility();
  const status = useIbkrStatus();
  const [prefs, setPrefs] = useState<NavRailPrefs>(readNavRailPrefs);

  const groups = useMemo(() => listScannerNavGroups(), []);
  const recordingSymbols =
    status.capture === true && status.recording === true ? (status.capture_symbols ?? []) : [];

  const dashboardUp = !traderActive && page === 'dashboard';
  // The Account page is a shell page; the legacy Account / Reports dashboard
  // tabs still light the item when something else selects them.
  const accountActive =
    (!traderActive && page === 'account') || (dashboardUp && isAccountTab(scanner.activeTab));
  const botsActive = dashboardUp && scanner.activeTab === 'strategy';
  const scannerActive = dashboardUp && !accountActive && !botsActive;
  // The list on the board keeps the highlight. HOD Momo / Running Up focus the
  // alert strip above it, so they get a quiet strip mark instead -- the rail
  // used to say "Running Up" over a board still reading "Losers" (QA V6).
  const childHighlight = dashboardUp ? scanner.activeTab : null;
  const stripFocus = dashboardUp && isDockTab(scanner.railHighlight) ? scanner.railHighlight : null;

  // Operator choice wins; otherwise the chrome follows the view (icons on the
  // Desk so the board gets the width, tree open on the Scanner).
  const collapsed = prefs.collapsed ?? navRailCollapsedDefault(page, traderActive);
  // Operator ask, 2026-09-22: the Scanner tree is open on every view until folded by hand.
  const folded = prefs.scannerFolded ?? false;

  const persist = useCallback((next: NavRailPrefs) => {
    setPrefs(next);
    writeNavRailPrefs(next);
  }, []);

  const toggleFold = () => persist({ ...prefs, scannerFolded: !folded });
  const toggleCollapse = () => persist({ ...prefs, collapsed: !collapsed });

  const leaveTrader = () => {
    if (traderActive) onLeaveTrader();
  };
  const goPage = (next: 'desk' | 'records' | 'account') => {
    leaveTrader();
    setNavPage(next);
  };
  const goTab = (tab: ActiveTab) => {
    leaveTrader();
    requestScannerTab(tab);
  };
  const goScanner = () => {
    if (scannerActive && !collapsed) {
      toggleFold();
      return;
    }
    goTab(scanner.lastListTab);
  };
  const goTrader = () => {
    if (traderActive) return;
    onOpenTrader((selectedSymbol?.trim() || TRADER_DEFAULT_SYMBOL).toUpperCase());
  };

  const treeId = 'nav-rail-scanner-tree';
  // Collapsed keeps the children as icons (tooltips carry the labels).
  const showTree = !folded;

  return (
    <nav
      className={`nav-rail${collapsed ? ' nav-rail--collapsed' : ''}${folded ? ' nav-rail--folded' : ''}`}
      aria-label={NAV_RAIL_ARIA_LABEL}
      data-testid="nav-rail"
      data-collapsed={collapsed ? 'true' : 'false'}
      data-active-tab={scanner.activeTab}
      data-rail-highlight={scanner.railHighlight}
    >
      <div className="nav-rail__list">
        <NavRailItem
          testId="nav-rail-desk"
          icon={navRailIcon('desk')}
          label={NAV_RAIL_LABEL_DESK}
          title={NAV_RAIL_TITLE_DESK}
          active={!traderActive && page === 'desk'}
          onClick={() => goPage('desk')}
        />
        <NavRailItem
          testId="nav-rail-trader"
          icon={navRailIcon('trader')}
          label={NAV_RAIL_LABEL_TRADER}
          title={NAV_RAIL_TITLE_TRADER}
          active={traderActive}
          onClick={goTrader}
        />

        <div className="nav-rail__tree">
          <div className="nav-rail__row">
            <NavRailItem
              testId="nav-rail-scanner"
              className="nav-rail__section"
              icon={navRailIcon('scanner')}
              label={NAV_RAIL_LABEL_SCANNER}
              title={NAV_RAIL_TITLE_SCANNER}
              active={scannerActive}
              ariaExpanded={showTree}
              ariaControls={treeId}
              onClick={goScanner}
            />
            {!collapsed && (
              <button
                type="button"
                className="nav-rail__chev"
                data-testid="nav-rail-scanner-chevron"
                aria-label={folded ? NAV_RAIL_UNFOLD_TITLE : NAV_RAIL_FOLD_TITLE}
                aria-expanded={showTree}
                aria-controls={treeId}
                title={folded ? NAV_RAIL_UNFOLD_TITLE : NAV_RAIL_FOLD_TITLE}
                onClick={toggleFold}
              >
                <NavRailChevron />
              </button>
            )}
          </div>
          {showTree && (
            <div id={treeId} data-testid={treeId}>
              {groups.map(({ group, modules }) => {
                const visible = modules.filter((m) => visibility[m.id] !== false);
                if (!visible.length) return null;
                return (
                  <div key={group} className="nav-rail__group" data-testid={`nav-rail-group-${group}`}>
                    <div className="nav-rail__grp">{NAV_RAIL_GROUP_LABELS[group]}</div>
                    {visible.map((m) => {
                      const dock = isDockTab(m.id as ActiveTab);
                      const n = m.countKey ? (scanner.counts[m.countKey] ?? 0) : 0;
                      return (
                        <NavRailItem
                          key={m.id}
                          testId={`nav-rail-tab-${m.id}`}
                          className={`nav-rail__child${stripFocus === m.id ? ' is-strip-focus' : ''}`}
                          dataTab={m.id}
                          icon={scannerNavIcon(m.id)}
                          label={m.title}
                          title={dock ? `${m.title}: ${NAV_RAIL_STRIP_FOCUS_TITLE}` : m.title}
                          count={formatScannerNavCount(n)}
                          countTitle={dock ? navRailAlertSymbolsTitle(n) : undefined}
                          active={!dock && childHighlight === m.id}
                          pressed={dock ? stripFocus === m.id : undefined}
                          onClick={() => goTab(m.id as ActiveTab)}
                        />
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {visibility.trading !== false && (
          <NavRailAccountItem active={accountActive} onOpen={() => goPage('account')} />
        )}
        {visibility.strategy !== false && (
          <NavRailItem
            testId="nav-rail-bots"
            icon={navRailIcon('bots')}
            label={NAV_RAIL_LABEL_BOTS}
            title={NAV_RAIL_TITLE_BOTS}
            active={botsActive}
            onClick={() => goTab('strategy')}
          />
        )}
        <NavRailItem
          testId="nav-rail-records"
          icon={navRailIcon('records')}
          label={NAV_RAIL_LABEL_RECORDS}
          title={
            recordingSymbols.length
              ? `${NAV_RAIL_LABEL_RECORDS}: ${navRailRecordingTitle(recordingSymbols.length, NAV_RAIL_RECORDING_MAX)}`
              : NAV_RAIL_TITLE_RECORDS
          }
          active={!traderActive && page === 'records'}
          onClick={() => goPage('records')}
          trailing={
            recordingSymbols.length ? (
              <span
                className="nav-rail__badge"
                data-testid="nav-rail-records-badge"
                title={navRailRecordingTitle(recordingSymbols.length, NAV_RAIL_RECORDING_MAX)}
              />
            ) : null
          }
        />
      </div>

      <div className="nav-rail__foot">
        <AdviseRailButton />
        {settings && (
          <NavRailItem
            testId="nav-rail-settings"
            icon={navRailIcon('settings')}
            label={NAV_RAIL_LABEL_SETTINGS}
            title={NAV_RAIL_TITLE_SETTINGS}
            active={settings.open}
            onClick={settings.toggle}
          />
        )}
        <button
          type="button"
          className="nav-rail__collapse"
          data-testid="nav-rail-collapse"
          aria-label={collapsed ? NAV_RAIL_EXPAND_TITLE : NAV_RAIL_COLLAPSE_TITLE}
          aria-pressed={collapsed}
          title={collapsed ? NAV_RAIL_EXPAND_TITLE : NAV_RAIL_COLLAPSE_TITLE}
          onClick={toggleCollapse}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>
    </nav>
  );
}
