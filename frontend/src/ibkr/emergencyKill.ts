/**
 * Emergency KILL compose -- existing doors only.
 * Desk lock first (nothing re-enters), then cancel -> flatten, then lock again.
 * ADR 072 retired the bots, so there is no bot level to set Off any more.
 *
 * Cancel-before-flatten is the invariant this module exists to hold: a resting
 * working order that survives the flatten can immediately re-open the position
 * that was just closed. Any gate added to this path is therefore ALL-OR-NOTHING
 * -- refusing one leg while another still fires produces a state neither branch
 * of the original design can reach. That is why the sample-desk check sits here,
 * ahead of every leg, rather than inside the individual doors (#357).
 *
 * The one exception is the operator's (#1281): KILL reads the venue once, at the
 * click, and names it on both legs. If the desk leaves that venue partway the
 * backend stops the leg and says what is still open, and nothing reaches the
 * venue the desk moved to. A stopped KILL is reported, never finished elsewhere.
 */
import { sampleKillRefusal } from '../sample_data/sampleOrderGuard';
import { getConfirmedDeskVenueSnapshot } from './confirmedDeskVenue';
import { flattenAccount } from './flattenAccount';
import { cancelAllWorkingOrders } from './placeOrder';
import { lockTicketSession } from './ticketUnlock';

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

/**
 * Disarm the backend latch. Fire and forget: the kill never waits on it, and
 * the cancel / flatten legs are exempt from the latch anyway. armDesk never
 * rejects; a refusal is logged, and the padlock shows the server's answer.
 */
function lockDesk(errors: string[]): void {
  try {
    void lockTicketSession().then((res) => {
      if (!res.ok) console.warn('[Nova] Emergency KILL could not lock the desk', res.code, res.message);
    });
  } catch (error) {
    pushError(errors, asError(error, 'Lock trading failed'));
  }
}


async function runEmergencyKillOnce(): Promise<EmergencyKillResult> {
  // The sample desk refuses the composite as one unit: no desk lock, no
  // cancel, no flatten. Nothing partial -- see the module header.
  // The caller (EmergencyKillButton) surfaces `errors` in a danger dialog, so
  // the operator is told plainly that nothing happened and where a real kill
  // lives, instead of reading a refusal while the account was flattened.
  const killRefusal = sampleKillRefusal();
  if (killRefusal) return { ok: false, errors: [killRefusal] };

  const errors: string[] = [];
  // Null before any status has answered: the backend then reads the desk's venue on arrival.
  const { venue } = getConfirmedDeskVenueSnapshot();

  lockDesk(errors);

  try {
    const cancel = await cancelAllWorkingOrders(undefined, venue);
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
    const flatten = await flattenAccount(venue);
    if (!flatten.ok) {
      pushError(errors, flatten.error?.trim() || 'Flatten all open positions failed');
    }
  } catch (error) {
    pushError(errors, asError(error, 'Flatten all open positions failed'));
  }

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
