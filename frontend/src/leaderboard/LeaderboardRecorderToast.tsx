/**
 * The Scanner board recorder runs whenever Nova does -- no button, no chip
 * (ADR 022). The one thing it says is a write failure: ONE toast when
 * `leaderboard_recorder.ok` flips to false, in the same toast the Session
 * Record uses for an unrequested stop. Dismissed, it stays gone until the
 * recorder recovers and fails again; a recovery clears it quietly.
 */
import { useEffect, useRef, useState } from 'react';
import { useIbkrStatus } from '../ibkr/useIbkrStatus';
import {
  LEADERBOARD_RECORDER_DISMISS,
  LEADERBOARD_RECORDER_FAILED_TITLE,
  leaderboardRecorderFailedBody,
} from './leaderboardConstants';

/** Toasts stack below each other at this pitch (RecordingSignals' own). */
const TOAST_TOP_PX = 64;
const TOAST_PITCH_PX = 96;

export function LeaderboardRecorderToast({ stackIndex = 0 }: { stackIndex?: number }) {
  const recorder = useIbkrStatus().leaderboard_recorder ?? null;
  const failing = recorder?.ok === false;
  const wasFailing = useRef(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (failing && !wasFailing.current) setOpen(true);
    if (!failing) setOpen(false);
    wasFailing.current = failing;
  }, [failing]);

  if (!open || !failing) return null;
  return (
    <div
      className="recording-stopped"
      role="alert"
      data-testid="leaderboard-recorder-toast"
      style={stackIndex ? { top: `${TOAST_TOP_PX + stackIndex * TOAST_PITCH_PX}px` } : undefined}
    >
      <div className="recording-stopped__text">
        <strong className="recording-stopped__title">{LEADERBOARD_RECORDER_FAILED_TITLE}</strong>
        <span className="recording-stopped__body">{leaderboardRecorderFailedBody(recorder?.error ?? null)}</span>
      </div>
      <div className="recording-stopped__actions">
        <button
          type="button"
          className="recording-stopped__dismiss"
          data-testid="leaderboard-recorder-toast-dismiss"
          aria-label={LEADERBOARD_RECORDER_DISMISS}
          title={LEADERBOARD_RECORDER_DISMISS}
          onClick={() => setOpen(false)}
        >
          ×
        </button>
      </div>
    </div>
  );
}
