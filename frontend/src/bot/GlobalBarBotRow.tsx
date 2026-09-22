import { GLOBAL_BAR_BOT_ROW_LABEL } from '../constants';
import { useNavRailSnapshot } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { BotArmControls } from './BotArmControls';
import { BotSymbolMenuHost } from './BotSymbolMenu';

/**
 * Shared bot chrome under GlobalAppBar -- parent and popped-out trader windows.
 * The arm controls (Level, Pack, Allowlist, Activate) live in the Trader and
 * Desk right-rail Bot Autonomy card (approved redesign, 2026-09-21) and on the
 * Bots page (the Strategy tab); every other view mounts only the symbol-menu
 * host, so the Scanner has no second row of chrome.
 */
const BOTS_PAGE_TAB = 'strategy';

export function GlobalBarBotRow() {
  const { traderViewActive } = useWorkspace();
  const nav = useNavRailSnapshot();
  const onBotsPage = !traderViewActive && nav.page === 'dashboard' && nav.scanner.activeTab === BOTS_PAGE_TAB;
  return (
    <div
      className={`global-app-bar__bot${onBotsPage ? '' : ' global-app-bar__bot--host-only'}`}
      data-testid="global-bar-bot"
      aria-label={GLOBAL_BAR_BOT_ROW_LABEL}
    >
      {onBotsPage && <BotArmControls />}
      <BotSymbolMenuHost />
    </div>
  );
}
