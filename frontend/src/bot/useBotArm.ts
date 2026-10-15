/**
 * The Bot switch (ADR 044), one logic for every surface that drives it (the header's switch beside the padlock, the
 * Trader rail card). Off always goes, and asks nothing: with it off no bot places an order, not even a sell, and
 * nothing is sold (operator decision 2026-10-15). On is locked with the reason where the bot cannot trade (Live, a
 * replay desk). Locking the padlock turns the Bot off in the backend (ibkr/safety's disarm path calls the bot), never
 * from here.
 */
import { DESK_BOT_POLL_MS } from '../constants';
import { setBotSessionError } from './botSessionPoller';
import { botOn, switchLock } from './botSwitch';
import { useBotSession } from './useBotSession';

export type BotArm = ReturnType<typeof useBotArm>;

export function useBotArm() {
  const bot = useBotSession(DESK_BOT_POLL_MS);
  const { session, busy, setSwitch } = bot;
  const on = session ? botOn(session) : false;
  const lock = switchLock(session, busy);

  /** Turn the Bot on or off, as the backend would accept it: refused with its reason. */
  async function onSwitch(next: boolean) {
    if (!next) return setSwitch(false);
    if (lock) {
      setBotSessionError(lock);
      return null;
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
