/**
 * Arm / disarm the backend desk latch (ADR 018) -- the padlock's only truth.
 *
 * The server owns "unlocked": every desk window, every pop-out and the
 * localhost bot API read one answer from the status poll, and a backend
 * restart (which always disarms) re-locks every padlock on the next poll.
 * Live arming carries the operator's PIN, which the backend checks against a
 * hash in `.env`; Paper and Sim arm without one. Nothing here stores or
 * compares a PIN.
 */
import { novaFetch } from '../api/novaFetch';
import {
  API_BASE_URL,
  DESK_ARM_NO_ANSWER_MESSAGE,
  DESK_ARM_REFUSED_MESSAGE,
} from '../constants';
import { SAMPLE_ORDER_REFUSAL } from '../sample_data/sampleCopy';
import { onSampleDesk } from '../sample_data/sampleOrderGuard';
import { refreshIbkrStatusNow } from './ibkrStatusPoller';

export type ArmDeskResult = {
  ok: boolean;
  /** The backend's refusal code (`ARM_PIN_INVALID`, ...), or null. */
  code: string | null;
  /** Operator-ready text for a refusal, shown as-is; null on success. */
  message: string | null;
};

const OK: ArmDeskResult = { ok: true, code: null, message: null };

/** The 403 body is `{detail, code}`; anything else still reads as a refusal. */
async function refusal(res: Response): Promise<ArmDeskResult> {
  let code: string | null = null;
  let message: string | null = null;
  try {
    const body = (await res.json()) as { detail?: unknown; code?: unknown } | null;
    if (typeof body?.code === 'string' && body.code.trim()) code = body.code.trim();
    if (typeof body?.detail === 'string' && body.detail.trim()) message = body.detail.trim();
  } catch (err) {
    console.warn('[Nova] desk arm refusal had no readable body', res.status, err);
  }
  return {
    ok: false,
    code,
    message: message ?? `${DESK_ARM_REFUSED_MESSAGE} (HTTP ${res.status})`,
  };
}

/**
 * Never throws. A failed arm leaves the desk disarmed and the backend keeps
 * refusing places -- the safe end. A failed disarm would leave the padlock
 * looking locked over an armed desk, so the status refresh below re-reads the
 * server either way and the UI corrects itself.
 */
export async function armDesk(armed: boolean, pin?: string): Promise<ArmDeskResult> {
  // V4: the arm latch is the live desk's; the sample desk never touches it.
  if (onSampleDesk()) return { ok: false, code: null, message: SAMPLE_ORDER_REFUSAL };
  const body: { armed: boolean; pin?: string; actor: 'operator' } = { armed, actor: 'operator' };
  if (armed && pin) body.pin = pin;
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/ibkr/arm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.ok ? OK : await refusal(res);
  } catch (err) {
    console.warn('[Nova] desk arm request failed', err);
    return { ok: false, code: null, message: DESK_ARM_NO_ANSWER_MESSAGE };
  } finally {
    refreshIbkrStatusNow();
  }
}
