import { createRoot } from 'react-dom/client';
import { BotNotices } from '../../src/bot/BotNotices';
import { LiveTraderBotsPage } from '../../src/bot/LiveTraderBotsPage';
import { AppDialogHost } from '../../src/ux/AppDialogHost';
import { installHoverTip } from '../../src/ux/hoverTip';
import { installWhyTip } from '../../src/ux/whyTip';
import '../../src/index.css';

/**
 * Bots > LiveTrader Bots (operator, 2026-10-15): the followed traders' page with the LiveTrader Bots key in its head and
 * each host's bot in their card, in the desk's slot (App.tsx: .nova-scanner-desk-slot), with the bot's notices. Every
 * API reply is the spec's.
 */
function Page() {
  return (
    <AppDialogHost>
      <div style={{ height: '100vh', display: 'flex', background: 'var(--nova-bg, #000)' }}>
        <div className="nova-scanner-desk-slot">
          <LiveTraderBotsPage />
        </div>
      </div>
      <BotNotices />
    </AppDialogHost>
  );
}

installHoverTip();
installWhyTip();
createRoot(document.getElementById('root')!).render(<Page />);
