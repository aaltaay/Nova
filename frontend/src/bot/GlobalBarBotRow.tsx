import { GLOBAL_BAR_BOT_ROW_LABEL } from '../constants';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { BotArmControls } from './BotArmControls';
import { BotSymbolMenuHost } from './BotSymbolMenu';

/**
 * Shared bot chrome under GlobalAppBar -- parent and popped-out trader windows.
 * On the Trader view the controls live in the right-rail Bot Autonomy card
 * (approved redesign, 2026-09-21), so only the symbol-menu host stays mounted
 * here; the Scanner keeps the full bar.
 */
export function GlobalBarBotRow() {
  const { traderViewActive } = useWorkspace();
  return (
    <div
      className={`global-app-bar__bot${traderViewActive ? ' global-app-bar__bot--host-only' : ''}`}
      data-testid="global-bar-bot"
      aria-label={GLOBAL_BAR_BOT_ROW_LABEL}
    >
      {!traderViewActive && <BotArmControls />}
      <BotSymbolMenuHost />
    </div>
  );
}
