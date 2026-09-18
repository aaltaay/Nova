/**
 * Emergency KILL compose -- existing doors only, in this order:
 * cancel-all -> account flatten -> Bot Autonomy L0 -> desk trade lock.
 * Cancel and flatten still run if the bot PATCH fails.
 */
import { patchBotSession } from '../bot/api';
import { refreshBotSessionNow } from '../bot/botSessionPoller';
import { flattenAccount } from './flattenAccount';
import { cancelAllWorkingOrders } from './placeOrder';
import { writeTicketSessionUnlocked } from './ticketUnlock';

export interface EmergencyKillResult {
  ok: boolean;
  errors: string[];
}

function asError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  const text = String(error ?? '').trim();
  return text || fallback;
}

export async function runEmergencyKill(): Promise<EmergencyKillResult> {
  const errors: string[] = [];

  try {
    const cancel = await cancelAllWorkingOrders();
    if (!cancel.ok) {
      errors.push(
        cancel.error?.trim()
        || (cancel.failed.length
          ? `Cancel all working orders: ${cancel.failed.length} failed`
          : 'Cancel all working orders failed'),
      );
    }
  } catch (error) {
    errors.push(asError(error, 'Cancel all working orders failed'));
  }

  try {
    const flatten = await flattenAccount();
    if (!flatten.ok) {
      errors.push(flatten.error?.trim() || 'Flatten all open positions failed');
    }
  } catch (error) {
    errors.push(asError(error, 'Flatten all open positions failed'));
  }

  try {
    await patchBotSession({ level: 0 });
  } catch (error) {
    errors.push(asError(error, 'Set Bot Autonomy to L0 failed'));
  }
  refreshBotSessionNow();

  try {
    writeTicketSessionUnlocked(false);
  } catch (error) {
    errors.push(asError(error, 'Lock trading failed'));
  }

  return { ok: errors.length === 0, errors };
}
