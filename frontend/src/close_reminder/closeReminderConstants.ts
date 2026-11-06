/**
 * The close-of-day reminder's numbers and words (operator ask, 2026-10-01: flat by 15:55 ET,
 * nothing held overnight). A Paper short names Nova's 15:55 day cover (ADR 048), and so does a Live short while
 * IBKR_SHORT_ENABLED is on (step 6: Live's cover runs only then). The bots' shares still held at 15:56 get their
 * own card (ADR 069 decision 9). Feature-local constants (AGENTS.md §6.1).
 */
import type { CloseReminder } from './closeReminderStore';

/** Minutes after midnight ET: the first card, the escalation, and when the cards leave. */
export const CLOSE_REMIND_WARN_MIN_ET = 15 * 60 + 50;
export const CLOSE_REMIND_FINAL_MIN_ET = 15 * 60 + 55;
export const CLOSE_REMIND_CLOSE_MIN_ET = 16 * 60;
/** The bots' card waits a minute past their sale: it shows only when that sale did not finish. */
export const CLOSE_REMIND_BOTS_MIN_ET = 15 * 60 + 56;
/** How often the cards re-read the clock and the positions. */
export const CLOSE_REMIND_TICK_MS = 1_000;
/** localStorage: the keys fired today, so a reload at 15:52 does not raise a dismissed card again. */
export const CLOSE_REMIND_FIRED_PREF_KEY = 'nova.closeReminder.fired';
export const CLOSE_REMIND_FIRED_SCHEMA_VERSION = 1;

export const CLOSE_REMIND_REGION = 'Close-of-day reminders';
export const CLOSE_REMIND_DISMISS = 'Dismiss';
export const closeReminderOpen = (symbol: string): string => `Open ${symbol}`;

const VENUE_WORDS: Record<CloseReminder['venue'], string> = { live: 'Live', paper: 'Paper' };

function sizeWords(qty: number): string {
  const n = Math.abs(qty);
  const shares = Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2);
  return qty < 0 ? `${shares} short` : shares;
}

/**
 * Nova covers a Paper short at 15:55 (ADR 048's day cover), and a Live short only while IBKR_SHORT_ENABLED is
 * on (#778 step 6): with the switch off a Live short was opened in TWS, and covering it is the operator's.
 */
function dayCover(r: Pick<CloseReminder, 'qty' | 'venue'>, liveCover: boolean): boolean {
  return r.qty < 0 && (r.venue === 'paper' || (r.venue === 'live' && liveCover));
}

export function closeReminderTitle(r: Pick<CloseReminder, 'symbol' | 'qty' | 'stage'> & Partial<Pick<CloseReminder, 'venue'>>,
  liveCover = false): string {
  const size = sizeWords(r.qty);
  if (r.stage === 'bots') return `15:56: the bots still hold ${size} ${r.symbol}`;
  const covers = dayCover({ qty: r.qty, venue: r.venue ?? 'live' }, liveCover);
  if (r.stage === 'final') {
    return covers ? `15:55: Nova covers ${size} ${r.symbol} now -- the day cover`
      : `15:55: ${size} ${r.symbol} still open -- close it now`;
  }
  return covers ? `Still holding ${size} ${r.symbol} at 15:50 -- cover it, or Nova covers it at 15:55`
    : `Still holding ${size} ${r.symbol} at 15:50 -- be flat by 15:55`;
}

export function closeReminderBody(r: Pick<CloseReminder, 'venue' | 'stale'> & Partial<Pick<CloseReminder, 'qty' | 'stage'>>,
  liveCover = false): string {
  if (r.stage === 'bots') {
    const close = (r.qty ?? 0) < 0 ? 'buys them back' : 'sells them';
    return `${VENUE_WORDS[r.venue]} · the bots' shares · Close on their row ${close}; nothing is held overnight`;
  }
  const venue = `${VENUE_WORDS[r.venue]} position`;
  const stale = r.stale ? ' · last known: the Gateway dropped' : '';
  if (dayCover({ qty: r.qty ?? 0, venue: r.venue }, liveCover)) {
    return `${venue}${stale} · at 15:55 Nova buys back what is left of a short, at market; nothing is held overnight`;
  }
  return `${venue}${stale} · the close is 16:00 ET; nothing is held overnight`;
}
