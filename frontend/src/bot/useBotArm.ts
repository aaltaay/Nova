/**
 * The bot's level and Activate, one logic for every surface that drives them
 * (the Bots page hero, the Trader rail card). Level 2 arms first; Activate is
 * refused while the desk gate blocks places or -- at Strategy -- while the
 * first-pullback read-out has not passed (ADR 027); locking the padlock
 * (disarming the desk) stops the bot.
 */
import { useEffect } from 'react';
import { BOT_ERROR_READOUT } from '../constantGroups/bot';
import { BOTS_ERROR_UNLOCK_FIRST } from '../constantGroups/bots_page';
import { DESK_BOT_POLL_MS } from '../constants';
import { botArmDisplayState } from '../ibkr/tradingAllowed';
import { useDeskTradingAllowed } from '../ibkr/useDeskTradingAllowed';
import { setBotSessionError } from './botSessionPoller';
import { useBotSession } from './useBotSession';

export type BotArm = ReturnType<typeof useBotArm>;

export function useBotArm() {
  const bot = useBotSession(DESK_BOT_POLL_MS);
  const { session, activate, stop, patch } = bot;
  const gate = useDeskTradingAllowed();
  const level = session?.level ?? 0;
  const armed = Boolean(session?.armed);
  const display = botArmDisplayState(armed, gate);
  const live = Boolean(session?.live_fire_ready) && display.looksActive;
  const readoutPassed = Boolean(session?.readout?.passed);
  // An absent read-out (older API) is not a pass; the backend refuses anyway.
  const readoutBlocks = level >= 2 && !readoutPassed;
  const activateBlocked = !gate.allowed || readoutBlocks;
  const activateReason = !gate.allowed
    ? gate.reason
    : readoutBlocks
      ? `${BOT_ERROR_READOUT}: ${session?.readout?.reason ?? 'not read yet'}`
      : null;

  // Only a fresh read that says "disarmed" stops the bot: a cached or failed
  // status cannot tell, and a bot may have armed the desk since (Paper / Sim).
  const deskDisarmed = gate.armKnown && gate.blockers.includes('pin');
  useEffect(() => {
    if (deskDisarmed && armed) void stop();
  }, [deskDisarmed, armed, stop]);

  async function onLevel(next: number) {
    // Raising to Strategy needs the desk token from Activate; with the
    // read-out closed the backend then lands it not active (ADR 027).
    if (next >= 2 && !armed) {
      // Say why instead of doing nothing: a click that changes nothing reads as a broken button.
      if (!gate.allowed) {
        setBotSessionError(`${BOTS_ERROR_UNLOCK_FIRST}${gate.reason ? ` (${gate.reason})` : ''}`);
        return;
      }
      if (!(await activate())) return;
    }
    await patch({ level: next });
  }

  async function onControl(next: boolean) {
    if (level < 2) return;
    if (next) {
      if (activateBlocked) {
        if (activateReason) setBotSessionError(activateReason);
        return;
      }
      await activate();
    } else await stop();
  }

  return {
    ...bot,
    gate,
    level,
    armed,
    display,
    live,
    readoutPassed,
    activateBlocked,
    activateReason,
    showKeyField: Boolean(bot.error && /api key/i.test(bot.error)),
    onLevel,
    onControl,
  };
}
