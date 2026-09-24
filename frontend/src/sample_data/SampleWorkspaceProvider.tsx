/**
 * The sample desk's own workspace (#449). The sample shell mounts inside the
 * live WorkspaceProvider (App.tsx), which keeps the operator's real Trader
 * tabs for when the sample desk is left. This provider shadows it for
 * everything under the sample shell: the selected symbol and the Trader tabs
 * are the sample desk's own, in memory (useSampleTraderDesk), so the Trader,
 * the Focus rail, the Desk and pop-out work there without touching the
 * operator's saved tabs, the dock bus or the bot's focus list.
 *
 * The rest -- the IB Gateway fields and the discovery defaults -- is the live
 * provider's value, which on the sample route already reads the sample status
 * (ibkrStatusPoller) and no backend config (sampleNetworkGate).
 */
import { useMemo, useState, type ReactNode } from 'react';
import { useWorkspace, WorkspaceValueProvider, type WorkspaceValue } from '../workspace';
import { parseSampleSymbol } from './sampleNav';
import { useSampleTraderDesk } from './useSampleTraderDesk';

/** The workspace fields the sample desk owns; every one is replaced, none read from the live desk. */
export const SAMPLE_OWNED_WORKSPACE_KEYS = [
  'selectedSymbol', 'setSelectedSymbol', 'openStockView', 'openTraderTab', 'selectRowSymbol',
  'extractTraderTab', 'acceptTraderTabDrop', 'requestDockTraderTab', 'traderWindowId', 'traderDeskRole',
  'traderDockOffer', 'publishTraderTabOffer', 'publishTraderTabOfferEnd', 'traderTabs', 'traderLiveTabs',
  'traderPinnedTabs', 'activeTraderSymbol', 'traderBlockNotice', 'dismissTraderBlockNotice',
  'activateTraderTab', 'closeTraderTab', 'pinTraderTab', 'unpinTraderTab', 'renameTraderTab',
  'addTraderDraftTab', 'closeTraderView', 'traderViewActive', 'showScannerView', 'traderMoveLocks',
] as const satisfies readonly (keyof WorkspaceValue)[];

type SampleOwned = Pick<WorkspaceValue, (typeof SAMPLE_OWNED_WORKSPACE_KEYS)[number]>;

export function SampleWorkspaceProvider({ children }: { children: ReactNode }) {
  const live = useWorkspace();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(() => parseSampleSymbol());
  const trader = useSampleTraderDesk(setSelectedSymbol);

  const owned = useMemo<SampleOwned>(() => ({
    selectedSymbol,
    setSelectedSymbol,
    openStockView: trader.openStockView,
    openTraderTab: trader.openTraderTab,
    selectRowSymbol: trader.selectRowSymbol,
    extractTraderTab: trader.extractTraderTab,
    acceptTraderTabDrop: trader.acceptTraderTabDrop,
    requestDockTraderTab: trader.requestDockTraderTab,
    traderWindowId: trader.windowId,
    traderDeskRole: trader.role,
    traderDockOffer: null,
    publishTraderTabOffer: trader.publishTraderTabOffer,
    publishTraderTabOfferEnd: trader.publishTraderTabOfferEnd,
    traderTabs: trader.traderState.tabs,
    traderLiveTabs: trader.traderState.live,
    traderPinnedTabs: trader.traderState.pinned,
    activeTraderSymbol: trader.traderState.active,
    traderBlockNotice: trader.traderBlockNotice,
    dismissTraderBlockNotice: trader.dismissTraderBlockNotice,
    activateTraderTab: trader.activateTraderTab,
    closeTraderTab: trader.closeTraderTab,
    pinTraderTab: trader.pinTraderTab,
    unpinTraderTab: trader.unpinTraderTab,
    renameTraderTab: trader.renameTraderTab,
    addTraderDraftTab: trader.addTraderDraftTab,
    closeTraderView: trader.closeTraderView,
    traderViewActive: trader.traderViewActive,
    showScannerView: trader.showScannerView,
    traderMoveLocks: trader.moveLocks,
  }), [selectedSymbol, trader]);

  const value = useMemo<WorkspaceValue>(() => ({ ...live, ...owned }), [live, owned]);
  return <WorkspaceValueProvider value={value}>{children}</WorkspaceValueProvider>;
}
