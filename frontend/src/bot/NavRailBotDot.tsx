/**
 * The nav rail's Bots item carries the bot's state as a dot (approved mockup
 * v4): amber while a level is chosen but the bot is not in control, green when
 * it is, nothing at Off or when there is no bot session (the sample desk).
 */
import { botArmDisplayState } from '../ibkr/tradingAllowed';
import { useDeskTradingAllowed } from '../ibkr/useDeskTradingAllowed';
import { botHeaderState } from './botHeaderState';
import { useBotSession } from './useBotSession';

export function NavRailBotDot() {
  const { session } = useBotSession();
  const gate = useDeskTradingAllowed();
  if (!session || session.level <= 0) return null;
  const view = botHeaderState(session, botArmDisplayState(Boolean(session.armed), gate).looksActive);
  return (
    <span
      className={`nav-rail__badge nav-rail__badge--bot nav-rail__badge--${view.tone}`}
      data-testid="nav-rail-bots-dot"
      title={view.title}
    />
  );
}
