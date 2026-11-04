/**
 * The Bots page's bottom line (approved mockup v4): the selected symbol and its
 * position, the bot's working orders, and the order kinds the localhost bot API may
 * send (the sleeve's `api_kinds`; Nova's own bot and Auto-entry use their own entry). On Paper it reads the bots'
 * own book: their shares in the stock and every bot's working orders (ADR 069 decision 9); Sim has one book.
 */
import { BOT_ACTION_KINDS } from '../constantGroups/bot';
import { BOTS_STATUS_FLAT, BOTS_STATUS_NO_SYMBOL, BOTS_STATUS_ORDER_KINDS, botsStatusHeld } from '../constantGroups/bots_page';
import { useDeskPositions } from '../ibkr';
import { useOptionalIbkrAccountContext } from '../ibkr/IbkrAccountContext';
import { useWorkspace } from '../workspace';
import type { BotSession } from './types';

export function BotsStatusBar({ session }: { session: BotSession }) {
  const { selectedSymbol } = useWorkspace();
  const account = useOptionalIbkrAccountContext();
  const { botsBook, split } = useDeskPositions();
  const sym = selectedSymbol?.trim().toUpperCase() || '';
  const held = sym ? account?.positions.find(p => p.symbol.toUpperCase() === sym)?.qty ?? 0 : 0;
  const qty = split ? botsBook.get(sym) ?? 0 : held;
  const working = split ? (account?.orders ?? []).filter(o => o.owner === 'bots').length : session.working.length;
  const shares = `${qty > 0 ? '+' : ''}${qty} sh`;
  const kinds = session.caps.api_kinds.length ? session.caps.api_kinds : [...BOT_ACTION_KINDS];
  return (
    <footer className="bots-status" data-testid="bots-status">
      <span>
        {sym || BOTS_STATUS_NO_SYMBOL} · {qty && split
          ? <b className="bots-status__held">{botsStatusHeld(shares)}</b>
          : qty ? shares : BOTS_STATUS_FLAT}
        {' · '}{working} bot working order{working === 1 ? '' : 's'}
      </span>
      <span className="bots-status__kinds">{BOTS_STATUS_ORDER_KINDS} {kinds.join(' · ')}</span>
    </footer>
  );
}
