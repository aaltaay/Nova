/**
 * The ambient and the loud half of a Session Record, mounted once with the
 * app bar: a 2px hairline along the top edge while recording, and a toast
 * that stays until resumed or dismissed when a recording stops without the
 * operator asking. The backend resumes on its own (capture/keepalive.py);
 * the toast reports that, and offers Resume now for when it gave up.
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import { getIbkrStatusSnapshot } from '../ibkr/ibkrStatusPoller';
import {
  RECORDING_DISMISS_LABEL,
  RECORDING_RESUME_ACTION,
  RECORDING_RESUMING_ACTION,
  RECORDING_SIGNAL_TICK_MS,
  recordingHairlineTitle,
  recordingResumeCountdown,
  recordingResumeGaveUp,
  recordingResumeWaiting,
  recordingStoppedBody,
  recordingStoppedTitle,
} from './constants';
import { stoppedView, type StoppedView } from './recordingSignalModel';
import {
  dismissRecordingStop,
  getRecordingSymbols,
  getSessionRecordVersion,
  isRecordingStopDismissed,
  startTabRecord,
  subscribeSessionRecord,
} from './sessionRecordStore';
import './recordingSignal.css';

function resumeLine(view: StoppedView): string | null {
  const resume = view.resume;
  if (!resume) return null;
  if (resume.gaveUp) return recordingResumeGaveUp(resume.gaveUpReason);
  const attempt = resume.attempt + 1;
  return resume.nextInSec > 0
    ? recordingResumeCountdown(resume.nextInSec, attempt, resume.maxAttempts)
    : recordingResumeWaiting(attempt, resume.maxAttempts);
}

export function RecordingSignals({ onOpenSymbol }: { onOpenSymbol?: (symbol: string) => void }) {
  useSyncExternalStore(subscribeSessionRecord, getSessionRecordVersion, () => 0);
  const status = getIbkrStatusSnapshot();
  const recordingSymbol = getRecordingSymbols()[0] ?? null;
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stopped = stoppedView(status, now);
  const shown = stopped && !isRecordingStopDismissed(stopped.key) ? stopped : null;
  const ticking = Boolean(shown?.resume?.pending);
  useEffect(() => {
    if (!ticking) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), RECORDING_SIGNAL_TICK_MS);
    return () => window.clearInterval(id);
  }, [ticking]);
  useEffect(() => { setError(null); }, [shown?.key]);

  const resume = async (symbol: string) => {
    setBusy(true);
    setError(null);
    const err = await startTabRecord(symbol);
    setBusy(false);
    if (err) setError(err);
  };

  return (
    <>
      {recordingSymbol && (
        <div
          className="recording-hairline"
          data-testid="recording-hairline"
          title={recordingHairlineTitle(recordingSymbol)}
          aria-hidden="true"
        />
      )}
      {shown && (
        <div className="recording-stopped" role="alert" data-testid="recording-stopped">
          <div className="recording-stopped__text">
            <strong className="recording-stopped__title">{recordingStoppedTitle(shown.symbol, shown.reason)}</strong>
            <span className="recording-stopped__body">{recordingStoppedBody(shown.error, shown.prints)}</span>
            {resumeLine(shown) && (
              <span className="recording-stopped__resume" data-testid="recording-stopped-resume">{resumeLine(shown)}</span>
            )}
            {error && <span className="recording-stopped__error">{error}</span>}
          </div>
          <div className="recording-stopped__actions">
            <button
              type="button"
              className="recording-stopped__action"
              data-testid="recording-stopped-resume-now"
              disabled={busy}
              onClick={() => void resume(shown.symbol)}
            >
              {busy ? RECORDING_RESUMING_ACTION : RECORDING_RESUME_ACTION}
            </button>
            {onOpenSymbol && (
              <button
                type="button"
                className="recording-stopped__action recording-stopped__action--secondary"
                data-testid="recording-stopped-open"
                onClick={() => onOpenSymbol(shown.symbol)}
              >
                Go to {shown.symbol}
              </button>
            )}
            <button
              type="button"
              className="recording-stopped__dismiss"
              data-testid="recording-stopped-dismiss"
              aria-label={RECORDING_DISMISS_LABEL}
              title={RECORDING_DISMISS_LABEL}
              onClick={() => dismissRecordingStop(shown.key)}
            >
              ×
            </button>
          </div>
        </div>
      )}
    </>
  );
}
