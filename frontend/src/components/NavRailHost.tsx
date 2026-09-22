/**
 * Live-desk wiring for the nav rail: Trader state from the workspace, the
 * Settings drawer from SettingsProvider. The sample shell wires NavRail itself.
 */
import { useCallback, useMemo } from 'react';
import { useSettingsOptional } from '../settings/SettingsContext';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { NavRail } from './NavRail';

export function NavRailHost() {
  const {
    traderTabs,
    traderViewActive,
    openStockView,
    closeTraderView,
    showScannerView,
  } = useWorkspace();
  const settingsApi = useSettingsOptional();
  const detachedTrader = traderTabs.length > 0 && parseStockViewSymbol() != null;

  // Same rule the header used: a pop-out float closes, the host desk keeps
  // its Trader tabs mounted (L2 / tape stay up) and just shows the scanner side.
  const leaveTrader = useCallback(() => {
    if (!traderViewActive) return;
    if (detachedTrader) closeTraderView();
    else showScannerView();
  }, [traderViewActive, detachedTrader, closeTraderView, showScannerView]);

  const settingsOpen = settingsApi?.settings.showSettings ?? false;
  const toggleSettings = settingsApi?.toggleSettings;
  const settings = useMemo(
    () => (toggleSettings ? { open: settingsOpen, toggle: toggleSettings } : null),
    [settingsOpen, toggleSettings],
  );

  // Same rule as the shell's `traderUp`: a Trader view with no tab left (the
  // last tab popped out) shows the Scanner / Desk, so the rail must not keep
  // highlighting Trader over it (QA V33). The workspace keeps the view flag so
  // a tab docked back restores the Trader.
  const traderUp = traderViewActive && traderTabs.length > 0;

  return (
    <NavRail
      traderActive={traderUp}
      onOpenTrader={openStockView}
      onLeaveTrader={leaveTrader}
      settings={settings}
    />
  );
}
