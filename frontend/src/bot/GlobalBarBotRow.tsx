import { GLOBAL_BAR_BOT_ROW_LABEL } from '../constants';
import { BotSymbolMenuHost } from './BotSymbolMenu';

/**
 * Bot chrome under GlobalAppBar -- the parent window only; a pop-out has no app
 * bar and mounts its own symbol-menu host (App.tsx). Only that host lives here now: the level and Activate are on the
 * Bots page hero (approved mockup v4, ADR 027) and in the Trader / Desk
 * right-rail Bot Autonomy card, so no view carries a second row of chrome.
 */
export function GlobalBarBotRow() {
  return (
    <div className="global-app-bar__bot global-app-bar__bot--host-only" data-testid="global-bar-bot" aria-label={GLOBAL_BAR_BOT_ROW_LABEL}>
      <BotSymbolMenuHost />
    </div>
  );
}
