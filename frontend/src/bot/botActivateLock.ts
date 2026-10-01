/**
 * Whether Activate can be pressed, and why not (ADR 042 B), pure. Activate is
 * enabled only when the backend would accept it: every `activate`-stage gate open
 * (venue, master level, a setup at Strategy, the padlock, a stock set to Bot). The
 * bot trip is the one closed gate Activate may still pass -- after the operator
 * reads, in words, that it re-enables the bot for today; the press then sends
 * `reenable: true`, never before.
 */
import { BOTS_SESSION_LOADING_WHY, botsReenableText } from '../constantGroups/bots_page';
import { closedGates, gateLine, type GateContext } from './botGateWords';
import { levelName, masterLevel } from './botLevels';
import { etTime, usdCents } from './botWhen';
import type { BotGate, BotSession } from './types';

export interface ActivateLock {
  /** Why Activate cannot be pressed now; null when it can. */
  why: string | null;
  /** The bot trip fired on this venue today: what Activate asks before it re-enables the bot. */
  reenable: string | null;
  /** Each closed Activate gate's sentence, in the backend's order. */
  waits: string[];
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function reenableText(session: BotSession, trip: BotGate | null): string {
  const d = trip?.detail ?? {};
  const at = (d.fired_at ?? session.soft_breaker?.at ?? null) as string | number | null;
  const pnl = num(d.pnl) ?? session.soft_breaker?.pnl ?? null;
  return botsReenableText(etTime(at), usdCents(pnl));
}

export function activateLock(session: BotSession | null | undefined, ctx: GateContext = {}): ActivateLock {
  if (!session) return { why: BOTS_SESSION_LOADING_WHY, reenable: null, waits: [] };
  if (!Array.isArray(session.gates)) {
    // An API without gates: say what the page can tell, never "every gate is open".
    const fired = session.soft_breaker?.fired === true || session.soft_breaker_fired === true;
    const level = masterLevel(session);
    const why = level < 2 ? `The master level is ${levelName(level)}: choose Strategy on the dial first.` : null;
    return { why, reenable: fired ? reenableText(session, null) : null, waits: why ? [why] : [] };
  }
  const trip = session.gates.find(g => g.id === 'bot_trip' && !g.ok) ?? null;
  const waits = closedGates(session.gates, 'activate')
    .filter(g => g.id !== 'bot_trip')
    .map(g => gateLine(g, ctx).why ?? `${g.id.replace(/_/g, ' ')} is closed.`);
  return {
    why: waits.length ? waits.join(' ') : null,
    reenable: trip ? reenableText(session, trip) : null,
    waits,
  };
}
