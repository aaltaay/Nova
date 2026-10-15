/**
 * The Bot switch in words (ADR 044), pure: whether it is on, why it is off, and why it cannot be turned on
 * here. The Bots page's Bot card, the Trader rail card and the header pill all read it, so the three never
 * disagree. On is the master at Strategy with Activate; off leaves the master at Eyes, so the strategies keep
 * alerting.
 */
import { BOTS_BUSY_WHY, BOTS_SESSION_LOADING_WHY } from '../constantGroups/bots_page';
import { isActive, masterLevel } from './botLevels';
import { gateLine } from './botGateWords';
import { deactivatedLine, prose } from './botsPageFormat';
import type { BotSession } from './types';

/** Why the switch is locked on Live while it is off: a bot never trades there yet. */
export const BOT_SWITCH_LIVE_WHY =
  'The bot trades on Paper and Sim only. On Live, your PIN padlock unlocks your own orders; the bot never trades Live.';

/** The switch is on: the backend's `bot_on`, else (an older backend) Activate with the master at Strategy. */
export function botOn(session: BotSession): boolean {
  return typeof session.bot_on === 'boolean' ? session.bot_on : isActive(session) && masterLevel(session) === 2;
}

/** The venue the switch belongs to (each venue keeps its own). */
export function switchVenue(session: BotSession): string | null {
  return session.switch?.venue ?? session.level_venue ?? null;
}

/** Why the Bot is off, in a sentence: the backend's reason, or plain off. */
export function offWords(session: BotSession): string {
  if (session.switch?.why_off) return prose(session.switch.why_off);
  const off = deactivatedLine(session.deactivated);
  if (off) return `${off}.`;
  return 'Off. The strategies at Eyes or On still alert you.';
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
