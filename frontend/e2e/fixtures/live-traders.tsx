import { createRoot } from 'react-dom/client';
import { BotNotices } from '../../src/bot/BotNotices';
import { LiveTraderBotsPage } from '../../src/bot/LiveTraderBotsPage';
import { IbkrAccountProvider } from '../../src/ibkr/IbkrAccountContext';
import { AppDialogHost } from '../../src/ux/AppDialogHost';
import { installHoverTip } from '../../src/ux/hoverTip';
import { installWhyTip } from '../../src/ux/whyTip';
import { WorkspaceProvider } from '../../src/workspace';
import '../../src/index.css';

/**
 * Bots > LiveTrader Bots (operator, 2026-10-15): the followed traders' page with the LiveTrader Bots key in its head and
 * each host's bot in their card, in the desk's slot (App.tsx: .nova-scanner-desk-slot), with the bot's notices and the
 * providers App.tsx puts above that slot (the Positions / Orders · today dock reads them). Every API reply is the spec's.
 */
function Page() {
  return (
    <AppDialogHost>
      <WorkspaceProvider>
      <IbkrAccountProvider>
      <div style={{ height: '100vh', display: 'flex', background: 'var(--nova-bg, #000)' }}>
        <div className="nova-scanner-desk-slot">
          <LiveTraderBotsPage />
        </div>
      </div>
      <BotNotices />
      </IbkrAccountProvider>
      </WorkspaceProvider>
    </AppDialogHost>
  );
}

installHoverTip();
installWhyTip();
createRoot(document.getElementById('root')!).render(<Page />);
