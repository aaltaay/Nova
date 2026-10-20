/**
 * No bot turns on while the desk padlock is locked (operator decision 2026-10-20): "If we activate any of the bots,
 * it shows us a screen that says, do you want to unlock the lock? ... ALL bots, strategy bots and future bots. Single
 * source of truth."
 *
 * The backend is the one truth (`backend/bot/padlock_gate.py`): every press that turns a bot on -- the Bot switch,
 * a family key, a strategy set On, a TraderTV host's Bot key, Activate, a bot added later -- is refused
 * `BOT_PADLOCK_LOCKED` over a locked padlock, and changes nothing. Every bot write goes through `withPadlockPrompt`,
 * so that refusal, from any surface, asks the same question: Yes unlocks the padlock (`POST /api/ibkr/arm`; bots
 * trade Paper and Sim, which unlock without a PIN, and the backend never asks this on Live) and presses again; Keep it
 * off leaves the bot off and the padlock locked. Nothing here unlocks without the operator's yes.
 */
import {
  BOT_PADLOCK_KEPT_OFF,
  BOT_PADLOCK_PROMPT_CANCEL,
  BOT_PADLOCK_PROMPT_CONFIRM,
  BOT_PADLOCK_PROMPT_MESSAGE,
  BOT_PADLOCK_PROMPT_TITLE,
  BOT_PADLOCK_REFUSAL_CODE,
  BOT_PADLOCK_UNLOCK_FAILED,
} from '../constantGroups/bot';
import { armDesk } from '../ibkr';
import { confirmApp } from '../ux/appDialogApi';
import { BotApiError } from './botApiError';

/** The backend refused a bot's On because the padlock is locked. */
export function isPadlockRefusal(err: unknown): err is BotApiError {
  return err instanceof BotApiError && err.code === BOT_PADLOCK_REFUSAL_CODE;
}

/**
 * Run a bot write; if it is refused for the locked padlock, ask to unlock it, unlock on yes and run it once more.
 * Any other refusal, a no, or a failed unlock throws in words the desk shows as they are.
 */
export async function withPadlockPrompt<T>(press: () => Promise<T>): Promise<T> {
  try {
    return await press();
  } catch (err) {
    if (!isPadlockRefusal(err)) throw err;
    const yes = await confirmApp({
      title: BOT_PADLOCK_PROMPT_TITLE,
      message: BOT_PADLOCK_PROMPT_MESSAGE,
      confirmLabel: BOT_PADLOCK_PROMPT_CONFIRM,
      cancelLabel: BOT_PADLOCK_PROMPT_CANCEL,
      tone: 'warning',
    });
    if (!yes) throw new BotApiError(BOT_PADLOCK_KEPT_OFF, err.code, err.status);
    const unlocked = await armDesk(true);
    if (!unlocked.ok) {
      const why = unlocked.message ? `: ${unlocked.message}` : '.';
      throw new BotApiError(`${BOT_PADLOCK_UNLOCK_FAILED}${why}`, unlocked.code ?? err.code, err.status);
    }
    return press();
  }
}
