/**
 * The Bot switch (ADR 044), one logic for every surface that drives it (the Bots page's Bot card, the
 * Trader rail card). Off always goes; on is locked with the reason where the bot cannot trade (Live, a
 * replay desk), and after the bot trip it asks in words before it sends `reenable: true`. Locking the
 * padlock turns the Bot off in the backend (ibkr/safety's disarm path calls the bot), never from here.
 */
import { DESK_BOT_POLL_MS } from '../constants';
import { confirmApp } from '../ux/appDialogApi';
import { setBotSessionError } from './botSessionPoller';
import { botOn, reenableWords, switchLock, tripLatch } from './botSwitch';
import { useBotSession } from './useBotSession';

export type BotArm = ReturnType<typeof useBotArm>;

export const BOT_REENABLE_TITLE = 'Turn the bot back on?';
export const BOT_REENABLE_YES = 'Turn on for today';
export const BOT_REENABLE_NO = 'Keep it off';

export function useBotArm() {
  const bot = useBotSession(DESK_BOT_POLL_MS);
  const { session, busy, setSwitch } = bot;
  const on = session ? botOn(session) : false;
  const lock = switchLock(session, busy);

  /** Turn the Bot on or off, as the backend would accept it: refused with its reason, or after the bot trip, asked first. */
  async function onSwitch(next: boolean) {
    if (!next) return setSwitch(false);
    if (lock) {
      setBotSessionError(lock);
      return null;
    }
    const latch = session ? tripLatch(session) : null;
    if (latch) {
      const yes = await confirmApp({
        title: BOT_REENABLE_TITLE,
        message: reenableWords(latch),
        confirmLabel: BOT_REENABLE_YES,
        cancelLabel: BOT_REENABLE_NO,
        tone: 'warning',
      });
      if (!yes) return null;
      return setSwitch(true, true);
    }
    return setSwitch(true);
  }

  return {
    ...bot,
    on,
    lock,
    showKeyField: Boolean(bot.error && /api key/i.test(bot.error)),
    onSwitch,
  };
}
