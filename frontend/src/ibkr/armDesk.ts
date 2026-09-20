/**
 * Arm / disarm the backend desk latch (ADR 018).
 *
 * The padlock's PIN stays the human challenge on the client; this is the truth
 * behind it. Putting the latch in the backend is the point of ADR 018: the
 * process that restarts is the one whose arming must not survive, and a
 * `sessionStorage` flag cannot notice an API restart at all.
 *
 * Because the server owns it, every pop-out desk window and the localhost bot
 * API read one answer from the status poll rather than a per-tab flag.
 */
import { novaFetch } from '../api/novaFetch';
import { API_BASE_URL } from '../constants';
import { refreshIbkrStatusNow } from './ibkrStatusPoller';

/**
 * Best-effort: never throws and never blocks the padlock.
 *
 * Failing open would be wrong in only one direction. If arming fails the desk
 * stays disarmed and the backend keeps refusing places, which is the safe end.
 * If disarming fails the padlock would look locked over an armed desk, so the
 * status refresh below re-reads the server and the UI corrects itself.
 */
export async function armDesk(armed: boolean): Promise<boolean> {
  try {
    const res = await novaFetch(`${API_BASE_URL}/api/ibkr/arm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ armed }),
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    refreshIbkrStatusNow();
  }
}
