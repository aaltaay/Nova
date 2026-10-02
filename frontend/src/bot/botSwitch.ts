/**
 * The Bot switch in words (ADR 044), pure: whether it is on, the bot trip's latch, why it is off, and why
 * it cannot be turned on here. The Bots page's Bot card, the Trader rail card and the header pill all read
 * it, so the three never disagree. On is the master at Strategy with Activate; off leaves the master at
 * Eyes, so the strategies keep alerting.
 */
import { BOTS_BUSY_WHY, BOTS_SESSION_LOADING_WHY } from '../constantGroups/bots_page';
import { isActive, masterLevel } from './botLevels';
import { gateLine } from './botGateWords';
import { deactivatedLine, prose } from './botsPageFormat';
import { etTime, etUntil, usdCents } from './botWhen';
import type { BotSession } from './types';

export interface TripLatch { at: string | number | null; pnl: number | null; until: string | number | null }

/** Why the switch is locked on Live while it is off: a bot never trades there yet. */
export const BOT_SWITCH_LIVE_WHY =
  'The bot does not trade on Live yet: your PIN padlock unlocks your own orders only. Its way to Live is #606, then your 1-share test.';

/** The switch is on: the backend's `bot_on`, else (an older backend) Activate with the master at Strategy. */
export function botOn(session: BotSession): boolean {
  return typeof session.bot_on === 'boolean' ? session.bot_on : isActive(session) && masterLevel(session) === 2;
}

const when = (v: unknown): string | number | null => (typeof v === 'string' || typeof v === 'number' ? v : null);

/** The bot trip's latch, from the switch's own words, the soft breaker or its gate; null when it has not fired. */
export function tripLatch(session: BotSession): TripLatch | null {
  if (session.switch?.latched) return session.switch.latched;
  const soft = session.soft_breaker;
  if (soft?.fired || session.soft_breaker_fired) return { at: soft?.at ?? null, pnl: soft?.pnl ?? null, until: soft?.until ?? null };
  const gate = (session.gates ?? []).find(g => g.id === 'bot_trip');
  if (!gate || gate.ok) return null;
  const d = gate.detail ?? {};
  return { at: when(d.fired_at), pnl: typeof d.pnl === 'number' ? d.pnl : null, until: when(d.until) };
}

/** The venue the switch belongs to (each venue keeps its own). */
export function switchVenue(session: BotSession): string | null {
  return session.switch?.venue ?? session.level_venue ?? null;
}

/** Why the Bot is off, in a sentence: the bot trip and when it lifts, the backend's reason, or plain off. */
export function offWords(session: BotSession): string {
  const latch = tripLatch(session);
  if (latch) return `Off since the bot trip${latch.at ? ` at ${etTime(latch.at)}` : ''}. It lifts at ${etUntil(latch.until) || '04:00'}.`;
  if (session.switch?.why_off) return prose(session.switch.why_off);
  const off = deactivatedLine(session.deactivated);
  if (off) return `${off}.`;
  return 'Off. The strategies at Eyes or On still alert you.';
}

/** The question asked before the switch turns on again after the bot trip. */
export function reenableWords(latch: TripLatch): string {
  const when = latch.at ? ` at ${etTime(latch.at)}` : '';
  const pnl = latch.pnl != null ? ` when the day's P&L hit ${usdCents(latch.pnl)}` : '';
  return `The bot trip fired${when}${pnl}. Turn the bot back on for the rest of today?`;
}

/** Why the switch cannot be pressed now, or null. Turning it off is never locked. */
export function switchLock(session: BotSession | null | undefined, busy: boolean): string | null {
  if (busy) return BOTS_BUSY_WHY;
  if (!session) return BOTS_SESSION_LOADING_WHY;
  if (botOn(session)) return null;
  if (switchVenue(session) === 'live') return BOT_SWITCH_LIVE_WHY;
  const venue = (session.gates ?? []).find(g => g.id === 'venue');
  if (venue && !venue.ok) {
    const line = gateLine(venue, {});
    return prose(line.why ?? line.text);
  }
  return null;
}
