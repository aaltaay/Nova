import { createRoot } from 'react-dom/client';
import { BotLiveTradersCard } from '../../src/bot/BotLiveTradersCard';
import { BotNotices } from '../../src/bot/BotNotices';
import { AppDialogHost } from '../../src/ux/AppDialogHost';
import { installHoverTip } from '../../src/ux/hoverTip';
import '../../src/index.css';
import '../../src/bot/botsPage.css';
import '../../src/bot/botsPageCards.css';
import '../../src/bot/botsOnePage.css';
import '../../src/bot/botTemplates.css';

/** The Live Trader section and the bot's notices as the Bots page draws them; every API reply is the spec's. */
function Page() {
  return (
    <AppDialogHost>
      <div className="bots-page" style={{ padding: 24, width: 1240 }}>
        <BotLiveTradersCard />
      </div>
      <BotNotices />
    </AppDialogHost>
  );
}

installHoverTip();
createRoot(document.getElementById('root')!).render(<Page />);
