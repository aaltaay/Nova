/**
 * The head of Bots > LiveTrader Bots, after the title (approved render, 2026-10-15): the LiveTrader Bots key and, while
 * the hosts' bots cannot trade, one line -- "No orders · " and what stops them (the desk off Paper, the Bot switch in
 * the header, this key, Freeze all orders, the feed), all of it on hover -- so no blocker is silent and none repeats on
 * every host. Freeze all orders is on Strategy Bots, so that line links there. A book or settings file the bot
 * cannot write says so in red. The page itself says when the desk has no TraderTV feed.
 */
import {
  LT_BOTS_PAGE_CODES,
  LT_LOADING,
  LT_NO_ORDERS,
  LT_OPEN_BOTS,
  LT_OPEN_BOTS_TIP,
} from '../constantGroups/live_trader';
import { tipProps } from '../ux';
import { setNavPage } from '../workspace';
import { BotFamilyKey } from './BotFamilyKey';
import { prose } from './botsPageFormat';
import { firstClause } from './liveTraderFormat';
import { useLiveTraders } from './liveTraderStore';
import './liveTraderStrip.css';

function HeadLine() {
  const { view, error } = useLiveTraders();
  if (!view) {
    return (
      <span className={`lt-head__held${error ? ' is-bad' : ' is-plain'}`} role="status" data-testid="lt-head-state"
        {...tipProps(error ? prose(error) : null)}>
        <i className="lt-dot" aria-hidden="true" /><span className="lt-head__why">{error ? firstClause(prose(error)) : LT_LOADING}</span>
      </span>
    );
  }
  if (!view.enabled) return null;
  const bad = view.settings_error || view.book_error;
  if (bad) {
    return (
      <span className="lt-head__held is-bad" role="alert" data-testid="lt-head-error" {...tipProps(prose(bad))}>
        <i className="lt-dot" aria-hidden="true" /><span className="lt-head__why">{firstClause(prose(bad))}</span>
      </span>
    );
  }
  if (view.can_trade.ok) return null;
  const why = prose(view.can_trade.why ?? '');
  const elsewhere = LT_BOTS_PAGE_CODES.includes(view.can_trade.code ?? '');
  return (
    <span className="lt-head__held" data-testid="lt-blocker" {...tipProps(why, LT_NO_ORDERS)}>
      <i className="lt-dot" aria-hidden="true" /><span className="lt-head__why">{LT_NO_ORDERS} · {firstClause(why)}</span>
      {elsewhere ? (
        <button type="button" className="lt-linkbtn" data-testid="lt-open-bots" onClick={() => setNavPage('bots-strategy')}
          {...tipProps(LT_OPEN_BOTS_TIP, LT_OPEN_BOTS)}>
          {LT_OPEN_BOTS}
        </button>
      ) : null}
    </span>
  );
}

export function LiveTraderHead() {
  return (
    <span className="lt-head" data-testid="lt-head">
      <BotFamilyKey family="live_trader" compact />
      <HeadLine />
    </span>
  );
}
