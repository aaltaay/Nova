/**
 * Global header Emergency KILL -- confirm, then compose existing doors.
 */
import { useRef, useState } from 'react';
import {
  APP_DIALOG_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_BODY,
  GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE,
  GLOBAL_BAR_EMERGENCY_KILL_FAIL_TITLE,
  GLOBAL_BAR_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_TITLE,
} from '../constants';
import { runEmergencyKill } from '../ibkr/emergencyKill';
import { alertApp, confirmApp } from '../ux';

export function EmergencyKillButton() {
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);

  async function onClick() {
    if (inflight.current) return;
    inflight.current = true;
    try {
      const ok = await confirmApp({
        title: GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE,
        message: GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_BODY,
        confirmLabel: APP_DIALOG_EMERGENCY_KILL_LABEL,
        tone: 'danger',
      });
      if (!ok) return;
      setBusy(true);
      try {
        const result = await runEmergencyKill();
        if (!result.ok) {
          await alertApp({
            title: GLOBAL_BAR_EMERGENCY_KILL_FAIL_TITLE,
            message: result.errors.join('\n'),
            tone: 'danger',
          });
        }
      } finally {
        setBusy(false);
      }
    } finally {
      inflight.current = false;
    }
  }

  return (
    <button
      type="button"
      className="global-app-bar__emergency-kill"
      title={GLOBAL_BAR_EMERGENCY_KILL_TITLE}
      aria-label={GLOBAL_BAR_EMERGENCY_KILL_LABEL}
      data-testid="global-bar-emergency-kill"
      disabled={busy}
      onClick={() => {
        void onClick();
      }}
    >
      {busy ? GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL : GLOBAL_BAR_EMERGENCY_KILL_LABEL}
    </button>
  );
}
