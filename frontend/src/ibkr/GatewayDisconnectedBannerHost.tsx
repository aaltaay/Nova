/**
 * App-level host so Open live/paper stays visible when DashboardPage is
 * hidden (Trader view). Same workspace + settings the scanner banner used.
 */
import { useSettings } from '../settings/SettingsContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { GatewayDisconnectedBanner } from './GatewayDisconnectedBanner';

export function GatewayDisconnectedBannerHost() {
  const {
    ibkrConnected,
    ibkrTransportConnected,
    ibkrPortsDark,
    ibkrDisconnectHint,
    ibkrSecondFactorStale,
    ibkrGatewayMode,
  } = useWorkspace();
  const { settings } = useSettings();
  return (
    <GatewayDisconnectedBanner
      discoveryProvider={settings.discoveryProvider}
      ibkrConnected={ibkrConnected}
      ibkrTransportConnected={ibkrTransportConnected}
      ibkrPortsDark={ibkrPortsDark}
      ibkrDisconnectHint={ibkrDisconnectHint}
      ibkrGatewayMode={ibkrGatewayMode}
      ibkrSecondFactorStale={ibkrSecondFactorStale}
    />
  );
}
