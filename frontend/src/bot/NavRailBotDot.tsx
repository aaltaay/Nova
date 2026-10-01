/**
 * The nav rail's Bots item carries the bot's state as a dot (approved mockup v4, ADR
 * 042): amber while the master level is Eyes or Strategy but the bot is not trading,
 * green while it is active and would trade, nothing at Off or when there is no bot
 * session (the sample desk). The hover says why.
 */
import { botHeaderState } from './botHeaderState';
import { useBotSession } from './useBotSession';

export function NavRailBotDot() {
  const { session } = useBotSession();
  if (!session || session.level <= 0) return null;
  const view = botHeaderState(session);
  return (
    <span
      className={`nav-rail__badge nav-rail__badge--bot nav-rail__badge--${view.tone}`}
      data-testid="nav-rail-bots-dot"
      title={view.title}
    />
  );
}
