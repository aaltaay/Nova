/**
 * The bot's state in a few words for the global bar pill, the nav rail dot and the
 * Trader rail card (approved mockup v4, ADR 042): the master level, how many setups are
 * at Strategy, and Active / Not active -- with the reason on hover, never a chosen
 * setup's name (there is none). Pure.
 */
import { BOT_LEVEL_LABELS, BOT_STATE_ACTIVE, BOT_STATE_NOT_ACTIVE } from '../constantGroups/bot';
import { BOTS_NOT_TRADING_NOW, botsAtStrategy } from '../constantGroups/bots_page';
import { activateLock } from './botActivateLock';
import { isActive, isReady, masterLevel, setupNames, strategySetups } from './botLevels';
import { deactivatedLine, prose, sessionVenueName } from './botsPageFormat';
import type { BotSession } from './types';

export type BotHeaderTone = 'off' | 'idle' | 'on';

export interface BotHeaderState {
  /** "L2" / "L1", or "" at Off. */
  level: string;
  /** The master level's name: "Strategy" / "Eyes" / "Off". */
  name: string;
  /** "2 at Strategy" at the Strategy master level; blank otherwise. */
  detail: string;
  /** "Active" / "Not active" at Strategy; blank below it. */
  state: string;
  tone: BotHeaderTone;
  /** The reason the bot is not trading, in a sentence; null when it is, or below Strategy. */
  reason: string | null;
  /** The hover text: the level, the setups at Strategy, the state and its reason, every closed gate. */
  title: string;
}

/** Why a Strategy bot is not trading now: why it was turned off, or what Activate waits on. */
function whyNot(session: BotSession): string | null {
  if (isActive(session)) {
    return isReady(session) ? null : `${BOTS_NOT_TRADING_NOW}${session.ready_reason ? ` — ${prose(session.ready_reason)}` : ''}`;
  }
  const off = deactivatedLine(session.deactivated);
  const lock = activateLock(session);
  return [off, lock.why ?? (lock.reenable ?? 'press Activate on the Bots page')].filter(Boolean).join(' · ');
}

export function botHeaderState(session: BotSession): BotHeaderState {
  const venue = sessionVenueName(session);
  const level = masterLevel(session);
  const closed = (session.gates ?? []).filter(g => !g.ok).map(g => g.id.replace(/_/g, ' '));
  const gatesText = Array.isArray(session.gates)
    ? closed.length ? `${closed.length} of ${session.gates.length} gates closed: ${closed.join(', ')}` : 'every gate is open'
    : 'gates not reported by this API';
  if (level <= 0) {
    return { level: '', name: BOT_LEVEL_LABELS[0], detail: '', state: '', tone: 'off', reason: null,
      title: `Bot off on ${venue}: no setup proposes or trades; every scanner still watches and scores in silence` };
  }
  if (level === 1) {
    return { level: 'L1', name: BOT_LEVEL_LABELS[1], detail: '', state: '', tone: 'idle', reason: null,
      title: `Eyes on ${venue}: setups at Eyes or Strategy propose on near + go; nothing trades, you place · ${gatesText}` };
  }
  const at = strategySetups(session);
  const active = isActive(session);
  const reason = whyNot(session);
  const stateText = active ? (reason ? `${BOT_STATE_ACTIVE} · ${reason}` : BOT_STATE_ACTIVE) : `${BOT_STATE_NOT_ACTIVE} — ${reason}`;
  return {
    level: 'L2',
    name: BOT_LEVEL_LABELS[2],
    detail: botsAtStrategy(at.length),
    state: active ? BOT_STATE_ACTIVE : BOT_STATE_NOT_ACTIVE,
    tone: active && reason == null ? 'on' : 'idle',
    reason,
    title: `Strategy on ${venue} · at Strategy: ${setupNames(at)} · ${stateText} · ${gatesText}`,
  };
}
