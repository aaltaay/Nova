/**
 * The bot's master level and Activate (ADR 042), one logic for every surface that
 * drives them (the Bots page hero, the Trader rail card). Choosing a level never
 * activates the bot: configuration is not "go". Activate is enabled only when the
 * backend would accept it (bot/botActivateLock.ts), and after a bot trip it asks in
 * words before it sends `reenable: true`. Locking the padlock turns the bot off in
 * the backend (ibkr/safety's disarm path calls the bot), never from here.
 */
import { BOTS_REENABLE_CANCEL, BOTS_REENABLE_OK, BOTS_REENABLE_TITLE } from '../constantGroups/bots_page';
import { DESK_BOT_POLL_MS } from '../constants';
import { confirmApp } from '../ux/appDialogApi';
import { activateLock } from './botActivateLock';
import { gateContext } from './botGateWords';
import { isActive, isReady, masterLevel } from './botLevels';
import { setBotSessionError } from './botSessionPoller';
import { useBotSession } from './useBotSession';

export type BotArm = ReturnType<typeof useBotArm>;

export function useBotArm() {
  const bot = useBotSession(DESK_BOT_POLL_MS);
  const { session, activate, patch } = bot;
  const level = masterLevel(session);
  const active = isActive(session);
  const ready = isReady(session);
  const lock = activateLock(session, session ? gateContext(session, null) : {});

  /** The master level: a PATCH, never an Activate. */
  async function onLevel(next: number) {
    await patch({ level: next });
  }

  /** Activate, as the backend would accept it: refused with its reason, or after the bot trip, asked first. */
  async function onActivate() {
    if (lock.why) {
      setBotSessionError(lock.why);
      return null;
    }
    if (lock.reenable) {
      const ok = await confirmApp({
        title: BOTS_REENABLE_TITLE,
        message: lock.reenable,
        confirmLabel: BOTS_REENABLE_OK,
        cancelLabel: BOTS_REENABLE_CANCEL,
        tone: 'warning',
      });
      if (!ok) return null;
      return activate({ reenable: true });
    }
    return activate();
  }

  return {
    ...bot,
    level,
    active,
    ready,
    lock,
    showKeyField: Boolean(bot.error && /api key/i.test(bot.error)),
    onLevel,
    onActivate,
  };
}
