/**
 * The global bar (approved redesign, 2026-09-22), mounted once in AppShell so
 * every live page inherits it. One row, left to right on every view:
 *
 *   wordmark · session chip · ET clock · connection chip · venue pills · REC
 *   chips · [ticker search, centred] · Emergency KILL · Day's / Working / TAV
 *   / bot pill / account pill · padlock · gear
 *
 * Reload backend, the theme toggle, the full Gateway & feed status cluster and
 * the sample-data door live under the gear (GlobalBarGearMenu); the Scanner's
 * history-date picker moved to the board header's session line. View
 * navigation is the nav rail's. Bot row = BotSymbolMenuHost only (issue #230;
 * ADR 027 moved the level and Activate to the Bots page hero); the Trader tab
 * row sits under it, above the chart. The watch list's toasts ("XYZ hit HOD
 * Momo", "XYZ: bull flag armed") mount here too, so they reach every page of
 * the main desk once.
 */
import { GLOBAL_BAR_BRAND } from '../constants';
import { RecordingChip } from '../capture/RecordingChip';
import { RecordingSignals } from '../capture/RecordingSignals';
import { GlobalBarBotPill } from '../bot/GlobalBarBotPill';
import { GlobalBarBotRow } from '../bot/GlobalBarBotRow';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { GatewayModeCapsule } from '../ibkr/GatewayModeCapsule';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { TradingSessionLockButton } from '../ibkr/TradingSessionLockButton';
import { isSampleView } from '../sample_data/sampleNav';
import { SimSessionHeader } from '../sim/SimSessionHeader';
import { StockViewMarketClock } from '../stock_view/StockViewMarketClock';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { EmergencyKillButton } from './EmergencyKillButton';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';
import { GlobalBarConnectionChip } from './GlobalBarConnectionChip';
import { GlobalBarGearMenu } from './GlobalBarGearMenu';
import { GlobalBarSessionChip } from './GlobalBarSessionChip';
import { GlobalBarTickerSearch } from './GlobalBarTickerSearch';
import { resolveAccountChromeState } from './globalBarAccountChrome';
import { setGlobalBarTraderSlot } from './globalBarSlots';
import { NovaLogo } from './NovaLogo';
import { useScannerBarProps } from './scannerBarStore';
import type { GlobalAppBarScanner } from './globalAppBarScanner';
import { useRenderCount } from '../perf/useRenderCount';
import { WatchListToasts } from '../watch_list/WatchListToasts';

export type { GlobalAppBarScanner };

export function GlobalAppBar({ scanner: scannerProp }: { scanner?: GlobalAppBarScanner }) {
  useRenderCount('GlobalAppBar');
  const liveScanner = useScannerBarProps();
  const scanner = scannerProp ?? liveScanner ?? null;
  const {
    traderTabs,
    traderViewActive,
    openStockView,
    closeTraderView,
    showScannerView,
    ibkrConnected,
    ibkrStatusKnown,
    ibkrStatusError,
    ibkrMode,
    deskVenue,
    ibkrGatewayMode,
    ibkrAccountKind,
    ibkrIntentionalMode,
    ibkrDisconnectHint,
  } = useWorkspace();
  const { summary, orders, positions, refresh, loading: accountLoading, error: accountError } =
    useIbkrAccountContext();
  const { orders: closedOrders } = useClosedOrders(ibkrConnected);

  const traderActive = traderViewActive;
  const detachedTrader = traderTabs.length > 0 && parseStockViewSymbol() != null;
  const leaveTraderToScanner = () => {
    if (!traderViewActive) return;
    if (detachedTrader) closeTraderView();
    else showScannerView();
  };
  // The host's lookup opens the symbol in its Trader (the live bridge publishes
  // openStockView; the sample shell its own); with nothing published yet, the
  // workspace's Trader is the door.
  const lookup = scanner?.onLookup ?? openStockView;

  const accountChrome = resolveAccountChromeState({
    // The sample desk owns its own account snapshot (#357). WorkspaceProvider
    // sits above the sample gate, so ibkrConnected is false there with no
    // backend -- and the header would say "IBKR offline" next to its own
    // GATEWAY-connected chip, the exact contradiction globalBarAccountChrome
    // warns against. isSampleView() is false on every live route.
    ibkrConnected: Boolean(ibkrConnected) || isSampleView(),
    summaryConnected: summary?.connected,
    loading: accountLoading,
    error: accountError,
    // Only an explicit false is "unknown" (resolveAccountChromeState's own contract).
    statusKnown: isSampleView() || ibkrStatusKnown,
    statusError: ibkrStatusError,
  });
  return (
    // The bar is tinted by the settled venue (global-app-bar.css); none while unknown.
    <header className="global-app-bar" data-testid="global-app-bar" data-venue={deskVenue ?? undefined}>
      <RecordingSignals onOpenSymbol={openStockView} />
      <WatchListToasts onOpenSymbol={openStockView} />
      <div className="global-app-bar__primary" data-testid="global-bar-primary">
        <div className="global-app-bar__left" data-testid="global-bar-left">
          <div className="global-app-bar__brand" aria-label={GLOBAL_BAR_BRAND}>
            <NovaLogo />
            <span className="global-app-bar__wordmark">{GLOBAL_BAR_BRAND}</span>
          </div>
          <GlobalBarSessionChip />
          <StockViewMarketClock />
          <GlobalBarConnectionChip
            scanner={scanner}
            ibkrConnected={Boolean(scanner?.ibkrConnected ?? ibkrConnected)}
            ibkrMode={scanner?.ibkrMode ?? ibkrMode}
            ibkrGatewayMode={scanner?.ibkrGatewayMode ?? ibkrGatewayMode}
            ibkrAccountKind={ibkrAccountKind}
          />
          <GatewayModeCapsule
            mode={ibkrMode}
            venue={deskVenue}
            gatewayMode={ibkrGatewayMode ?? undefined}
            accountKind={ibkrAccountKind}
            intentionalMode={ibkrIntentionalMode}
            disconnectHint={ibkrDisconnectHint}
            testId="header-gateway-mode-capsule"
          />
          <RecordingChip variant="bar" onOpenSymbol={openStockView} />
        </div>

        <div className="global-app-bar__center" data-testid="global-bar-center">
          <GlobalBarTickerSearch onLookup={lookup} tabs={traderTabs} positions={positions} />
        </div>

        <div className="global-app-bar__right" data-testid="global-bar-right">
          <EmergencyKillButton />
          <GlobalBarAccountCluster
            accountChrome={accountChrome}
            accountError={accountError}
            summary={summary}
            orders={orders}
            closedOrders={closedOrders}
            traderActive={traderActive}
            closeTraderView={leaveTraderToScanner}
            refresh={refresh}
            venue={deskVenue}
            beforePill={<GlobalBarBotPill />}
          />
          <TradingSessionLockButton />
          <GlobalBarGearMenu
            scanner={scanner}
            ibkrAccountKind={ibkrAccountKind}
            ibkrIntentionalMode={ibkrIntentionalMode}
            onOpenSymbol={openStockView}
          />
        </div>
      </div>
      <GlobalBarBotRow />
      {/* Host desk only — pop-out floats render tabs inline above the chart. */}
      {traderActive && !detachedTrader ? (
        <div
          ref={setGlobalBarTraderSlot}
          className="global-app-bar__trader-row"
          data-testid="global-bar-trader-slot"
        />
      ) : null}
      <SimSessionHeader active={deskVenue === 'sim'} />
    </header>
  );
}
