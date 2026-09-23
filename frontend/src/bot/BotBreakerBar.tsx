/**
 * The two locked loss breakers on one scale (approved mockup v4): -$200 locks
 * the day, -$50 trips the bot, and a marker at the account's day P&L the
 * breakers compare (GET /api/bot/pnl). An unknown P&L draws no marker.
 */
import { BOT_BREAKER_HINT, BOT_HARD_BREAKER_USD, BOT_SOFT_BREAKER_USD } from '../constantGroups/bot';
import {
  BOTS_BREAKER_TODAY,
  BOTS_BREAKER_TODAY_UNKNOWN,
  BOTS_BREAKERS_LOCKED,
  BOTS_BREAKERS_TITLE,
} from '../constantGroups/bots_page';
import { fmtUsd, fmtUsdCents } from './botsPageFormat';

/** Where `v` sits on the hard-breaker .. $0 scale, 0-100 (a gain pins to the right end). */
export function breakerPosition(v: number): number {
  const span = Math.abs(BOT_HARD_BREAKER_USD);
  return Math.max(0, Math.min(100, ((v - BOT_HARD_BREAKER_USD) / span) * 100));
}

export function BotBreakerBar({ dayPnl }: { dayPnl: number | null }) {
  const soft = breakerPosition(BOT_SOFT_BREAKER_USD);
  const tone = dayPnl == null ? '' : dayPnl <= BOT_SOFT_BREAKER_USD ? ' is-bad' : dayPnl < 0 ? ' is-warn' : ' is-ok';
  return (
    <div className="bots-breakers" data-testid="bot-strategy-breakers" title={BOT_BREAKER_HINT}>
      <div className="bots-breakers__head">
        <span>{BOTS_BREAKERS_TITLE}</span>
        <span className="bots-breakers__lock">🔒 {BOTS_BREAKERS_LOCKED}</span>
      </div>
      <div className="bots-breakers__bar" aria-hidden="true">
        <i className="bots-breakers__tick bots-breakers__tick--hard" style={{ left: '0%' }} />
        <i className="bots-breakers__tick bots-breakers__tick--soft" style={{ left: `${soft}%` }} />
        {dayPnl != null ? (
          <i className={`bots-breakers__now${tone}`} data-testid="bots-breaker-now" style={{ left: `${breakerPosition(dayPnl)}%` }} />
        ) : null}
      </div>
      <div className="bots-breakers__labels">
        <span><b className="is-bad">{fmtUsd(BOT_HARD_BREAKER_USD)}</b> all-stop · day lock</span>
        <span style={{ left: `${soft}%` }} className="bots-breakers__soft"><b className="is-warn">{fmtUsd(BOT_SOFT_BREAKER_USD)}</b> bot trip</span>
        <span className={`bots-breakers__today${tone}`} data-testid="bots-breaker-today">
          {dayPnl == null ? BOTS_BREAKER_TODAY_UNKNOWN : <><b>{fmtUsdCents(dayPnl)}</b> {BOTS_BREAKER_TODAY}</>}
        </span>
      </div>
    </div>
  );
}
