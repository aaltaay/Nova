import { GLOBAL_BAR_BOT_ROW_LABEL } from '../constants';
import { BotArmControls } from './BotArmControls';
import { BotSymbolMenuHost } from './BotSymbolMenu';

/** Shared bot chrome under GlobalAppBar -- parent and popped-out trader windows. */
export function GlobalBarBotRow() {
  return (
    <div
      className="global-app-bar__bot"
      data-testid="global-bar-bot"
      aria-label={GLOBAL_BAR_BOT_ROW_LABEL}
    >
      <BotArmControls />
      <BotSymbolMenuHost />
    </div>
  );
}
