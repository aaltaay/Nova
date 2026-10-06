import { createRoot } from 'react-dom/client';
import { BotBreakerBar } from '../../src/bot/BotBreakerBar';
import { breakers } from '../../src/bot/botsPageFixtures';
import { useBotDayPnl } from '../../src/bot/useBotDayPnl';
import { installHoverTip } from '../../src/ux/hoverTip';
import '../../src/index.css';
import '../../src/bot/botsPage.css';
import '../../src/bot/botsPageCards.css';

/** Production P&L read and hover; API replies are mocked and controls disabled. */
function Meter() {
  const day = useBotDayPnl();
  return (
    <main style={{ padding: 48, width: 680 }}>
      <BotBreakerBar breakers={breakers({ venue: 'live' })} dayPnl={day.pnl}
        pnlParts={day.parts} busy={true} patch={async () => undefined} />
    </main>
  );
}

installHoverTip();
createRoot(document.getElementById('root')!).render(<Meter />);
