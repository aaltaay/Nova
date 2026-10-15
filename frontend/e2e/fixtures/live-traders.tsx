import { createRoot } from 'react-dom/client';
import { BotLiveTradersCard } from '../../src/bot/BotLiveTradersCard';
import { BotNotices } from '../../src/bot/BotNotices';
import { AppDialogHost } from '../../src/ux/AppDialogHost';
import { installHoverTip } from '../../src/ux/hoverTip';
import '../../src/index.css';
import '../../src/followed_traders/followed.css';

/**
 * The Live Trader panel and the bot's notices as the TraderTV LIVE page draws them (ADR 044 amendment, 2026-10-15):
 * at the top of the page, with none of the Bots page's sheets -- the panel carries its own look. Every API reply is
 * the spec's.
 */
function Page() {
  return (
    <AppDialogHost>
      <div className="ft-page" style={{ padding: 24, width: 1240 }}>
        <div className="ft-lt">
          <BotLiveTradersCard />
        </div>
      </div>
      <BotNotices />
    </AppDialogHost>
  );
}

installHoverTip();
createRoot(document.getElementById('root')!).render(<Page />);
