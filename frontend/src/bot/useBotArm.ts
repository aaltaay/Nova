/**
 * The Bot switch (ADR 044), one logic for every surface that drives it (the Bots page's Bot card, the
 * Trader rail card). Off always goes; on is locked with the reason where the bot cannot trade (Live, a
 * replay desk). Locking the padlock turns the Bot off in the backend (ibkr/safety's disarm path calls the
 * bot), never from here.
 */
import { DESK_BOT_POLL_MS } from '../constants';
import { LT_BOT_OFF_TITLE, LT_KEEP_ON, ltBotOffMessage, ltSellAndOff } from '../constantGroups/live_trader';
import { confirmApp } from '../ux/appDialogApi';
import { setBotSessionError } from './botSessionPoller';
import { fetchLiveTraderAsks } from './liveTraderApi';
import { heldBy } from './liveTraderFormat';
import { botOn, switchLock } from './botSwitch';
import { useBotSession } from './useBotSession';

export type BotArm = ReturnType<typeof useBotArm>;

/** What the Live Trader bot holds now; none when the desk has no such bot or it cannot say. */
async function liveTraderHeld() {
  try {
    return heldBy((await fetchLiveTraderAsks()).held);
  } catch {
    return [];
  }
}

export function useBotArm() {
  const bot = useBotSession(DESK_BOT_POLL_MS);
  const { session, busy, setSwitch } = bot;
  const on = session ? botOn(session) : false;
  const lock = switchLock(session, busy);

  /** Turn the Bot on or off, as the backend would accept it: refused with its reason. */
  async function onSwitch(next: boolean) {
    if (!next) {
      // The Live Trader bot's positions are sold when you turn Paper's bot off (ADR 055): asked first, by name.
      const held = session?.level_venue === 'paper' ? await liveTraderHeld() : [];
      if (held.length) {
        const yes = await confirmApp({
          title: LT_BOT_OFF_TITLE,
          message: ltBotOffMessage(held),
          confirmLabel: ltSellAndOff(held.length),
          cancelLabel: LT_KEEP_ON,
          tone: 'warning',
        });
        if (!yes) return null;
      }
      return setSwitch(false);
    }
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
