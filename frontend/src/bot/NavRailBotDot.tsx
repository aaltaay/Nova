/**
 * The nav rail's Bots item carries the Bot switch as a dot (ADR 044): green while the Bot is on and would
 * trade a GO trigger, amber while it is on but not trading now, nothing while it is off or when there is
 * no bot session (the sample desk). The hover says why.
 */
import { botHeaderState } from './botHeaderState';
import { useBotSession } from './useBotSession';

export function NavRailBotDot() {
  const { session } = useBotSession();
  if (!session) return null;
  const view = botHeaderState(session);
  if (!view.on) return null;
  return (
    <span
      className={`nav-rail__badge nav-rail__badge--bot nav-rail__badge--${view.tone}`}
      data-testid="nav-rail-bots-dot"
      title={view.title}
    />
  );
}
