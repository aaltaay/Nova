import { createRoot } from 'react-dom/client';
import { TopOfBookProvider } from '../../src/hotkeys/TopOfBookContext';
import { GatewayModeCapsule } from '../../src/ibkr/GatewayModeCapsule';
import { TickerTradeActionBar } from '../../src/ibkr/TickerTradeActionBar';
import { useIbkrStatus } from '../../src/ibkr/useIbkrStatus';
import { explicitVenueOf } from '../../src/ibkr/deskVenue';
import { TradeSettingsSection } from '../../src/settings/TradeSettingsSection';
import { useBotSession } from '../../src/bot/useBotSession';
import '../../src/index.css';

/** Production controls kept mounted on one symbol; all API traffic is mocked. */
function Desk() {
  const status = useIbkrStatus();
  const bot = useBotSession(2_500);
  const venue = explicitVenueOf(status);
  return (
    <main style={{ padding: 24 }}>
      <GatewayModeCapsule mode={status.mode} venue={venue} />
      <output data-testid="confirmed-venue">{venue ?? 'unknown'}</output>
      <output data-testid="bot-venue-level">
        {bot.session ? `${bot.session.level_venue}:${bot.session.level}` : 'loading'}
      </output>
      <section style={{ display: 'flex', gap: 24, alignItems: 'start' }}>
        <TradeSettingsSection />
        <div style={{ width: 360 }}>
          <TickerTradeActionBar
            symbol="GRML"
            mode={venue ?? 'disconnected'}
            connected={status.connected}
            spendStatus="disarmed"
            position={null}
            summary={null}
            referencePrice={8.6}
            variant="rail"
          />
        </div>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<TopOfBookProvider><Desk /></TopOfBookProvider>);
