/**
 * Global header Emergency KILL -- confirm, then compose existing doors.
 *
 * A red stop sign (operator ask, 2026-09-22: the text button read too loud);
 * hovering or focusing it opens a card that says exactly what a click will do,
 * and a click still asks for confirmation before anything runs.
 */
import { useRef, useState } from 'react';
import { Tooltip } from 'radix-ui';
import {
  APP_DIALOG_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_BUSY_WHY,
  GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_BODY,
  GLOBAL_BAR_EMERGENCY_KILL_CONFIRM_TITLE,
  GLOBAL_BAR_EMERGENCY_KILL_FAIL_TITLE,
  GLOBAL_BAR_EMERGENCY_KILL_HINT,
  GLOBAL_BAR_EMERGENCY_KILL_LABEL,
  GLOBAL_BAR_EMERGENCY_KILL_OPS,
  GLOBAL_BAR_EMERGENCY_KILL_TOOLTIP_DELAY_MS,
} from '../constants';
import { GLOBAL_BAR_EMERGENCY_KILL_SAMPLE_TITLE } from '../constantGroups/global_bar';
import { runEmergencyKill } from '../ibkr/emergencyKill';
import { sampleKillRefusal } from '../sample_data/sampleOrderGuard';
import { alertApp, confirmApp } from '../ux';
import { StopSignIcon } from './StopSignIcon';
import './emergencyKill.css';

/** What a click does, in the order it happens. */
export function EmergencyKillCard({ busy }: { busy: boolean }) {
  return (
    <div className="global-app-bar__kill-card" data-testid="global-bar-emergency-kill-card">
      <div className="global-app-bar__kill-card-title">
        {busy ? GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL : GLOBAL_BAR_EMERGENCY_KILL_LABEL}
      </div>
      <ul>
        {GLOBAL_BAR_EMERGENCY_KILL_OPS.map((op) => (
          <li key={op}>{op}</li>
        ))}
      </ul>
      <p>{GLOBAL_BAR_EMERGENCY_KILL_HINT}</p>
    </div>
  );
}

export function EmergencyKillButton() {
  const [busy, setBusy] = useState(false);
  const inflight = useRef(false);

  async function onClick() {
    if (inflight.current) return;
    inflight.current = true;
    try {
      // The sample desk refuses before the real kill's confirm, under its own
      // title -- never "did not finish cleanly" over a kill that never ran (V39).
      const sampleRefusal = sampleKillRefusal();
      if (sampleRefusal) {
        await alertApp({ title: GLOBAL_BAR_EMERGENCY_KILL_SAMPLE_TITLE, message: sampleRefusal, tone: 'warning' });
        return;
      }
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

  const label = busy ? GLOBAL_BAR_EMERGENCY_KILL_BUSY_LABEL : GLOBAL_BAR_EMERGENCY_KILL_LABEL;
  return (
    <Tooltip.Provider delayDuration={GLOBAL_BAR_EMERGENCY_KILL_TOOLTIP_DELAY_MS}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            className={`global-app-bar__emergency-kill${busy ? ' is-busy' : ''}`}
            aria-label={label}
            aria-busy={busy}
            data-testid="global-bar-emergency-kill"
            disabled={busy}
            data-why={busy ? GLOBAL_BAR_EMERGENCY_KILL_BUSY_WHY : undefined}
            onClick={() => {
              void onClick();
            }}
          >
            <StopSignIcon />
            <span className="sr-only">{label}</span>
          </button>
        </Tooltip.Trigger>
        {/* While KILL runs the locked stop sign answers with its reason (ux/whyTip.ts),
            so the what-a-click-does card stays shut rather than stack on it. */}
        {!busy && (
          <Tooltip.Portal>
            <Tooltip.Content className="global-app-bar__kill-tip" side="bottom" align="end" sideOffset={6} collisionPadding={8}>
              <EmergencyKillCard busy={busy} />
            </Tooltip.Content>
          </Tooltip.Portal>
        )}
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
