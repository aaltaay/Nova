/**
 * The Bot switch in a few words for the global bar pill and the Trader rail card (ADR 044): ON or OFF on
 * this venue, how many strategies are On, and -- on hover -- why it is off or why it is not trading now,
 * with every closed gate. On over a locked padlock it reads LOCKED, never ON: no bot places an order while the
 * padlock is locked (operator decision 2026-10-20, `padlockPrompt`). Pure.
 */
import { BOT_SWITCH_LOCKED_NAME, BOT_SWITCH_LOCKED_REASON } from '../constantGroups/bot';
import { BOTS_NOT_TRADING_NOW, botsStrategiesOn } from '../constantGroups/bots_page';
import { isShortSetup } from '../constantGroups/short_setups';
import { isReady, ownStrategySetups, setupLabelOf } from './botLevels';
import { prose, sessionVenueName } from './botsPageFormat';
import { botOn, offWords } from './botSwitch';
import type { BotSession } from './types';

export type BotHeaderTone = 'off' | 'idle' | 'locked' | 'on';

export interface BotHeaderState {
  on: boolean;
  /** "ON" / "OFF" / "LOCKED" (on, but the padlock blocks every order). */
  name: string;
  /** "2 strategies On". */
  detail: string;
  /** off: the switch is off; locked: on, but the padlock is locked; idle: on, but it would not trade a GO trigger
   *  now; on: on and ready. */
  tone: BotHeaderTone;
  /** Why it is off, or why it is not trading now; null while it would trade. */
  reason: string | null;
  /** The hover text: the switch, the strategies at On, the reason, every closed gate. */
  title: string;
}

/** The strategies at On, each with its side (ADR 049): "First pullback ▲ long, Bear flag ▼ short". */
function sidedNames(session: BotSession, ids: readonly string[]): string {
  if (!ids.length) return 'none';
  return ids.map(id => {
    const side = (session.setups ?? []).find(s => s.id === id)?.side ?? (isShortSetup(id) ? 'short' : 'long');
    return `${setupLabelOf(id)} ${side === 'short' ? '▼ short' : '▲ long'}`;
  }).join(', ');
}

export function botHeaderState(session: BotSession): BotHeaderState {
  const venue = sessionVenueName(session);
  const on = botOn(session);
  const strategies = ownStrategySetups(session);
  const detail = botsStrategiesOn(strategies.length);
  const closed = (session.gates ?? []).filter(g => !g.ok).map(g => g.id.replace(/_/g, ' '));
  const gatesText = Array.isArray(session.gates)
    ? closed.length ? `${closed.length} of ${session.gates.length} gates closed: ${closed.join(', ')}` : 'every gate is open'
    : 'gates not reported by this API';
  if (!on) {
    const reason = offWords(session);
    return { on, name: 'OFF', detail, tone: 'off', reason,
      title: `Bot off on ${venue}: ${reason} Strategies at On: ${sidedNames(session, strategies)}.` };
  }
  if ((session.gates ?? []).some(g => g.id === 'padlock' && !g.ok)) {
    return { on, name: BOT_SWITCH_LOCKED_NAME, detail, tone: 'locked', reason: BOT_SWITCH_LOCKED_REASON,
      title: `Bot on ${venue}, but locked: ${BOT_SWITCH_LOCKED_REASON}. Strategies at On: ${sidedNames(session, strategies)} · ${gatesText}` };
  }
  const reason = isReady(session) ? null : `${BOTS_NOT_TRADING_NOW}${session.ready_reason ? ` — ${prose(session.ready_reason)}` : ''}`;
  return {
    on,
    name: 'ON',
    detail,
    tone: reason ? 'idle' : 'on',
    reason,
    title: `Bot on ${venue} · strategies at On: ${sidedNames(session, strategies)} · ${reason ?? 'ready for a GO trigger'} · ${gatesText}`,
  };
}
