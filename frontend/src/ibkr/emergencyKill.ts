/**
 * Emergency KILL compose -- existing doors only.
 * L0 + desk lock first (stop bot re-entry), then cancel -> flatten,
 * then L0 + lock again. Cancel and flatten still run if a bot PATCH fails.
 *
 * Cancel-before-flatten is the invariant this module exists to hold: a resting
 * working order that survives the flatten can immediately re-open the position
 * that was just closed. Any gate added to this path is therefore ALL-OR-NOTHING
 * -- refusing one leg while another still fires produces a state neither branch
 * of the original design can reach. That is why the sample-desk check sits here,
 * ahead of every leg, rather than inside the individual doors (#357).
 */
import { patchBotSession } from '../bot/api';
import { refreshBotSessionNow } from '../bot/botSessionPoller';
import { sampleKillRefusal } from '../sample_data/sampleOrderGuard';
import { flattenAccount } from './flattenAccount';
import { cancelAllWorkingOrders } from './placeOrder';
import { writeTicketSessionUnlocked } from './ticketUnlock';

export interface EmergencyKillResult {
  ok: boolean;
  errors: string[];
}

let inflight: Promise<EmergencyKillResult> | null = null;

function asError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  const text = String(error ?? '').trim();
  return text || fallback;
}

function pushError(errors: string[], message: string): void {
  if (!errors.includes(message)) errors.push(message);
}

function lockDesk(errors: string[]): void {
  try {
    writeTicketSessionUnlocked(false);
  } catch (error) {
    pushError(errors, asError(error, 'Lock trading failed'));
  }
}

async function dropAutonomyL0(
  errors: string[],
  alreadyOk: { value: boolean },
): Promise<void> {
  if (alreadyOk.value) return;
  try {
    await patchBotSession({ level: 0 });
    alreadyOk.value = true;
  } catch (error) {
    pushError(errors, asError(error, 'Set Bot Autonomy to L0 failed'));
  }
  refreshBotSessionNow();
}

async function runEmergencyKillOnce(): Promise<EmergencyKillResult> {
  // The sample desk refuses the composite as one unit: no bot PATCH, no desk
  // lock, no cancel, no flatten. Nothing partial -- see the module header.
  // The caller (EmergencyKillButton) surfaces `errors` in a danger dialog, so
  // the operator is told plainly that nothing happened and where a real kill
  // lives, instead of reading a refusal while the account was flattened.
  const killRefusal = sampleKillRefusal();
  if (killRefusal) return { ok: false, errors: [killRefusal] };

  const errors: string[] = [];
  const l0 = { value: false };

  lockDesk(errors);
  await dropAutonomyL0(errors, l0);

  try {
    const cancel = await cancelAllWorkingOrders();
    if (!cancel.ok) {
      pushError(
        errors,
        cancel.error?.trim()
          || (cancel.failed.length
            ? `Cancel all working orders: ${cancel.failed.length} failed`
            : 'Cancel all working orders failed'),
      );
    }
  } catch (error) {
    pushError(errors, asError(error, 'Cancel all working orders failed'));
  }

  try {
    const flatten = await flattenAccount();
    if (!flatten.ok) {
      pushError(errors, flatten.error?.trim() || 'Flatten all open positions failed');
    }
  } catch (error) {
    pushError(errors, asError(error, 'Flatten all open positions failed'));
  }

  await dropAutonomyL0(errors, l0);
  lockDesk(errors);

  return { ok: errors.length === 0, errors };
}

export async function runEmergencyKill(): Promise<EmergencyKillResult> {
  if (inflight) return inflight;
  inflight = runEmergencyKillOnce().finally(() => {
    inflight = null;
  });
  return inflight;
}
