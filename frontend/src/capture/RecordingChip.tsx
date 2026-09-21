/**
 * Header REC chip: exists only while a recording runs. Red dot, symbol and
 * elapsed time; the tooltip carries the counts. Click opens the tab.
 */
import { Disc } from 'lucide-react';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { getIbkrStatusSnapshot } from '../ibkr/ibkrStatusPoller';
import {
  RECORDING_CHIP_ROLE,
  RECORDING_SIGNAL_TICK_MS,
  recordingChipTitle,
  recordingChipValue,
} from './constants';
import { elapsedLabel, recordingView } from './recordingSignalModel';
import { getRecordingSymbols, getSessionRecordVersion, subscribeSessionRecord } from './sessionRecordStore';
import './recordingSignal.css';

export function RecordingChip({ onOpenSymbol }: { onOpenSymbol?: (symbol: string) => void }) {
  useSyncExternalStore(subscribeSessionRecord, getSessionRecordVersion, () => 0);
  const status = getIbkrStatusSnapshot();
  const symbol = getRecordingSymbols()[0] ?? null;
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!symbol) return undefined;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), RECORDING_SIGNAL_TICK_MS);
    return () => window.clearInterval(id);
  }, [symbol]);
  const view = symbol ? recordingView(status, symbol, now) : null;
  if (!symbol) return null;

  // "For how long" is this segment: after a resume the session began earlier
  // than the recording has actually been running, and the tooltip says both.
  const elapsed = elapsedLabel(view?.segmentSinceMs ?? view?.sinceMs ?? null);
  const value = recordingChipValue(symbol, elapsed);
  const title = view
    ? recordingChipTitle({ ...view, elapsed, sessionElapsed: elapsedLabel(view.sinceMs) })
    : `Recording ${symbol}`;
  return (
    <button
      type="button"
      className="status-chip status-chip--compact status-chip--recording"
      data-testid="status-chip-recording"
      title={title}
      aria-label={`${RECORDING_CHIP_ROLE} ${value}`}
      onClick={(e) => { e.preventDefault(); onOpenSymbol?.(symbol); }}
    >
      <span className="dot recording" />
      <Disc className="status-chip__icon" aria-hidden="true" />
      <span className="status-chip__role">{RECORDING_CHIP_ROLE}</span>
      <span className="status-chip__value">{value}</span>
    </button>
  );
}
