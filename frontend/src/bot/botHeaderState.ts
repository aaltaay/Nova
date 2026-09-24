/**
 * The bot's state in a few words for the global bar pill and the nav rail dot
 * (approved mockup v4): "L2 First pullback · Not active". Pure.
 */
import { BOT_LEVEL_LABELS, BOT_SETUP_LABELS, BOT_STATE_ACTIVE, BOT_STATE_NOT_ACTIVE } from '../constantGroups/bot';
import type { BotSession } from './types';

export type BotHeaderTone = 'off' | 'idle' | 'on';

export interface BotHeaderState {
  /** "L2" / "L1", or "" at Off. */
  level: string;
  /** The setup that plays, or "Off". */
  name: string;
  /** "Not active" / "Active" / "Eyes"; blank at Off. */
  state: string;
  tone: BotHeaderTone;
  /** The hover text: every closed gate by name. */
  title: string;
}

export function botHeaderState(session: BotSession, looksActive: boolean): BotHeaderState {
  const level = session.level > 2 ? 2 : session.level;
  if (level <= 0) {
    return { level: '', name: BOT_LEVEL_LABELS[0], state: '', tone: 'off', title: 'Bot is off: the bot API is dark; the setup scanner still watches and proposes' };
  }
  const name = BOT_SETUP_LABELS[session.setup ?? ''] ?? session.setup ?? '';
  const closed = (session.gates ?? []).filter(g => !g.ok).map(g => g.id.replace(/_/g, ' '));
  const gatesText = Array.isArray(session.gates)
    ? closed.length ? `${closed.length} of ${session.gates.length} gates closed: ${closed.join(', ')}` : 'every gate is open'
    : 'gates not reported by this API';
  if (level === 1) {
    return { level: 'L1', name, state: BOT_LEVEL_LABELS[1], tone: 'idle', title: `Eyes: a connected bot may watch and propose, you place · ${gatesText}` };
  }
  return {
    level: 'L2',
    name,
    state: looksActive ? BOT_STATE_ACTIVE : BOT_STATE_NOT_ACTIVE,
    tone: looksActive ? 'on' : 'idle',
    title: `Strategy ${looksActive ? 'is in control' : 'is not active'} · ${gatesText}`,
  };
}
