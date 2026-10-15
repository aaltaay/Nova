import { createRoot } from 'react-dom/client';
import { BotNotices } from '../../src/bot/BotNotices';
import { LiveTraderBotsPage } from '../../src/bot/LiveTraderBotsPage';
import { AppDialogHost } from '../../src/ux/AppDialogHost';
import { installHoverTip } from '../../src/ux/hoverTip';
import '../../src/index.css';

/**
 * Bots > LiveTrader Bots (operator decision 2026-10-15): the LiveTrader Bots key on top, then the Live Trader panel
 * with its own look, and the bot's notices. Every API reply is the spec's.
 */
function Page() {
  return (
    <AppDialogHost>
      <div style={{ width: 1240, height: 900, display: 'flex' }}>
        <LiveTraderBotsPage />
      </div>
      <BotNotices />
    </AppDialogHost>
  );
}

installHoverTip();
createRoot(document.getElementById('root')!).render(<Page />);
