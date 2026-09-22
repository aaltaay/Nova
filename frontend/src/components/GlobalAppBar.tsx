/**
 * Webull-style chrome shared by Scanner and Trader View (parent + pop-out).
 * Mounted once in AppShell so every live page inherits it automatically.
 *
 * Primary row = brand, status, theme, account cluster (Day's / Working / TAV /
 * account pill -- GlobalBarAccountCluster), lock, Settings (icon). View
 * navigation (Desk / Trader / Scanner / Account / ...) is the nav rail's.
 * Bot row = BotArmControls + BotSymbolMenuHost (issue #230).
 * Trader tabs row = symbol strip under Bot Autonomy, above the chart.
 * Narrow widths hide low-value chips on the primary row
 * (global-app-bar-responsive.css); the bot row wraps/scrolls on its own.
 */
import {
  GLOBAL_BAR_BRAND,
  GLOBAL_BAR_SETTINGS_LABEL,
  GLOBAL_BAR_SETTINGS_TITLE,
} from '../constants';
import { useClosedOrders } from '../closed_orders/useClosedOrders';
import { useIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { TradingSessionLockButton } from '../ibkr/TradingSessionLockButton';
import { isSampleView } from '../sample_data/sampleNav';
import { useSettingsOptional } from '../settings/SettingsContext';
import { parseStockViewSymbol } from '../utils/stockViewNav';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { GlobalBarAccountCluster } from './GlobalBarAccountCluster';
import { resolveAccountChromeState } from './globalBarAccountChrome';
import { NovaLogo } from './NovaLogo';
import { GatewayModeCapsule } from '../ibkr/GatewayModeCapsule';
import { setGlobalBarTraderSlot } from './globalBarSlots';
import { HeaderConnectionStatus } from './HeaderConnectionStatus';
import { RecordingSignals } from '../capture/RecordingSignals';
import { EmergencyKillButton } from './EmergencyKillButton';
import { GlobalBarBotRow } from '../bot/GlobalBarBotRow';
import { SimSessionHeader } from '../sim/SimSessionHeader';
import { GlobalBarScannerCluster } from './GlobalBarScannerCluster';
import { ThemeToggle } from './ThemeToggle';
import { useScannerBarProps } from './scannerBarStore';
import {
  SCANNER_MODE_LABELS,
  type GlobalAppBarScanner,
} from './globalAppBarScanner';

export type { GlobalAppBarScanner };

export function GlobalAppBar({ scanner: scannerProp }: { scanner?: GlobalAppBarScanner }) {
  const liveScanner = useScannerBarProps();
  const scanner = scannerProp ?? liveScanner ?? undefined;
  const {
    traderTabs,
    traderViewActive,
    openStockView,
    closeTraderView,
    showScannerView,
    ibkrConnected,
    ibkrMode,
    ibkrGatewayMode,
    ibkrAccountKind,
    ibkrIntentionalMode,
    ibkrDisconnectHint,
  } = useWorkspace();
  const { summary, orders, refresh, loading: accountLoading, error: accountError } =
    useIbkrAccountContext();
  const { orders: closedOrders } = useClosedOrders(ibkrConnected);
  const settingsApi = useSettingsOptional();

  const traderActive = traderViewActive;
  const detachedTrader = traderTabs.length > 0 && parseStockViewSymbol() != null;
  const leaveTraderToScanner = () => {
    if (!traderViewActive) return;
    if (detachedTrader) closeTraderView();
    else showScannerView();
  };
  const settingsOpen = settingsApi?.settings.showSettings ?? false;

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
  });
  return (
    <header className="global-app-bar" data-testid="global-app-bar">
      <RecordingSignals onOpenSymbol={openStockView} />
      <div className="global-app-bar__primary" data-testid="global-bar-primary">
      <div className="global-app-bar__left">
        <div className="global-app-bar__brand" aria-label={GLOBAL_BAR_BRAND}>
          <NovaLogo />
          <span className="global-app-bar__wordmark">{GLOBAL_BAR_BRAND}</span>
        </div>
      </div>

      <div className="global-app-bar__center" data-testid="global-bar-center">
        {!traderActive && scanner && <GlobalBarScannerCluster scanner={scanner} />}
        {(traderActive || !scanner) && <EmergencyKillButton />}
        {scanner && (
          <div className="global-app-bar__status" data-testid="global-bar-status">
            <span className={`mode-badge mode-${scanner.mode}`}>
              {scanner.sampleDataActive ? 'Sample data' : SCANNER_MODE_LABELS[scanner.mode]}
            </span>
            <HeaderConnectionStatus
              health={scanner.health}
              discoveryProvider={scanner.discoveryProvider}
              ibkrConnected={scanner.ibkrConnected}
              ibkrMode={scanner.ibkrMode}
              ibkrGatewayMode={scanner.ibkrGatewayMode}
              ibkrAccountKind={ibkrAccountKind}
              ibkrIntentionalMode={ibkrIntentionalMode}
              activeFeed={scanner.activeFeed}
              feedFellBack={scanner.feedFellBack}
              secondsAgo={scanner.secondsAgo}
              lastPriceTs={scanner.lastPriceTs}
              pricesStale={scanner.pricesStale}
              honestyText={scanner.honestyText}
              historyDate={scanner.historyDate}
              compact
              showScannerSource={scanner.showScannerSource ?? true}
              onBackendStarted={scanner.onBackendStarted}
              onOpenSymbol={openStockView}
            />
          </div>
        )}
      </div>

      <div className="global-app-bar__right">
        <ThemeToggle />
        <GlobalBarAccountCluster
          accountChrome={accountChrome}
          accountError={accountError}
          summary={summary}
          orders={orders}
          closedOrders={closedOrders}
          traderActive={traderActive}
          closeTraderView={leaveTraderToScanner}
          refresh={refresh}
          venue={ibkrMode}
        />

        {!scanner && (
          <GatewayModeCapsule
            mode={ibkrMode}
            gatewayMode={ibkrGatewayMode ?? undefined}
            accountKind={ibkrAccountKind}
            intentionalMode={ibkrIntentionalMode}
            disconnectHint={ibkrDisconnectHint}
            testId="header-gateway-mode-capsule"
          />
        )}

        <TradingSessionLockButton />

        {settingsApi && (
          <button
            type="button"
            className={`global-app-bar__settings global-app-bar__icon-btn${settingsOpen ? ' is-active' : ''}`}
            title={GLOBAL_BAR_SETTINGS_TITLE}
            aria-label={GLOBAL_BAR_SETTINGS_LABEL}
            aria-pressed={settingsOpen}
            data-testid="global-bar-settings"
            onClick={() => settingsApi.toggleSettings()}
          >
            <span aria-hidden="true">⚙</span>
          </button>
        )}
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
      <SimSessionHeader active={ibkrMode === 'sim'} />
    </header>
  );
}
