/**
 * What the loss breakers did today on the desk venue (ADR 032, ADR 042 D): when the
 * bot trip fired and at what P&L, when the all-stop locked buys on this venue and
 * until when (the next 04:00 ET), and -- on a Sim replay -- that the breakers compare
 * nothing, because a replay's P&L is not today's. Nothing here is invented: an
 * unknown time or P&L is left out, never filled.
 */
import { BOTS_VENUE_NAMES, botsDayLocked, botsSoftFired } from '../constantGroups/bots_page';
import { etTime, etUntil, usdCents } from './botWhen';
import type { BotSession } from './types';

export function BotBreakerStatus({ session }: { session: BotSession }) {
  const soft = session.soft_breaker;
  const lock = session.day_lock;
  const note = session.breakers?.note ?? null;
  const venue = BOTS_VENUE_NAMES[String(lock?.venue ?? session.breakers?.venue ?? '')] ?? 'this venue';
  const softFired = soft?.fired === true || session.soft_breaker_fired === true;
  const locked = lock?.active === true || session.day_lock_active === true;
  if (!softFired && !locked && !note) return null;
  return (
    <div className="bots-breakers__status" data-testid="bots-breaker-status">
      {locked ? (
        <p className="is-bad" data-testid="bots-breaker-day-lock">
          {botsDayLocked(venue, etTime(lock?.tripped_at ?? null), usdCents(lock?.pnl ?? null),
            etUntil(lock?.until ?? session.hard_lock_until_date ?? null))}
        </p>
      ) : null}
      {softFired ? (
        <p className="is-warn" data-testid="bots-breaker-soft-fired">
          {botsSoftFired(etTime(soft?.at ?? null), usdCents(soft?.pnl ?? null), etUntil(soft?.until ?? null))}
        </p>
      ) : null}
      {note ? <p className="bots-muted" data-testid="bots-breaker-note">{note.replace(/ -- /g, ' — ')}</p> : null}
    </div>
  );
}
