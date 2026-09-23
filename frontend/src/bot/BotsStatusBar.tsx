/**
 * The Bots page's bottom line (approved mockup v4): the selected symbol and its
 * position, the bot's working orders, and the order kinds the bot may send.
 */
import { BOT_ACTION_KINDS } from '../constantGroups/bot';
import { BOTS_STATUS_FLAT, BOTS_STATUS_NO_SYMBOL, BOTS_STATUS_ORDER_KINDS } from '../constantGroups/bots_page';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useWorkspace } from '../workspace/WorkspaceContext';
import type { BotSession } from './types';

export function BotsStatusBar({ session }: { session: BotSession }) {
  const { selectedSymbol } = useWorkspace();
  const account = useOptionalIbkrAccountContext();
  const sym = selectedSymbol?.trim().toUpperCase() || '';
  const qty = sym ? account?.positions.find(p => p.symbol.toUpperCase() === sym)?.qty ?? 0 : 0;
  const working = session.working.length;
  const kinds = session.caps.allowlist.length ? session.caps.allowlist : [...BOT_ACTION_KINDS];
  return (
    <footer className="bots-status" data-testid="bots-status">
      <span>
        {sym || BOTS_STATUS_NO_SYMBOL} · {qty ? `${qty > 0 ? '+' : ''}${qty} sh` : BOTS_STATUS_FLAT}
        {' · '}{working} bot working order{working === 1 ? '' : 's'}
      </span>
      <span className="bots-status__kinds">{BOTS_STATUS_ORDER_KINDS} {kinds.join(' · ')}</span>
    </footer>
  );
}
