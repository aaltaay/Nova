/**
 * Header REC chips: one per recording symbol (up to three), none otherwise.
 * Red dot, symbol and elapsed time; the tooltip carries the counts. Click
 * opens that tab. `variant="bar"` is the redesigned global bar's chip
 * (`● REC GRML 5:12`, words on screen); the default stays the compact
 * icon chip the status cluster uses.
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
import { elapsedClockLabel, elapsedLabel, recordingView } from './recordingSignalModel';
import { getRecordingSymbols, getSessionRecordVersion, subscribeSessionRecord } from './sessionRecordStore';
import './recordingSignal.css';

interface Props {
  onOpenSymbol?: (symbol: string) => void;
  variant?: 'compact' | 'bar';
}

export function RecordingChip({ onOpenSymbol, variant = 'compact' }: Props) {
  useSyncExternalStore(subscribeSessionRecord, getSessionRecordVersion, () => 0);
  const status = getIbkrStatusSnapshot();
  const symbols = getRecordingSymbols();
  const key = symbols.join(',');
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!key) return undefined;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), RECORDING_SIGNAL_TICK_MS);
    return () => window.clearInterval(id);
  }, [key]);
  if (!symbols.length) return null;

  return (
    <>
      {symbols.map((symbol) => {
        const view = recordingView(status, symbol, now);
        // "For how long" is this segment: after a resume the session began earlier
        // than the recording has actually been running, and the tooltip says both.
        const segmentMs = view?.segmentSinceMs ?? view?.sinceMs ?? null;
        const elapsed = elapsedLabel(segmentMs);
        const value = recordingChipValue(symbol, elapsed);
        const title = view
          ? recordingChipTitle({ ...view, elapsed, sessionElapsed: elapsedLabel(view.sinceMs) })
          : `Recording ${symbol}`;
        const open = (e: React.MouseEvent) => { e.preventDefault(); onOpenSymbol?.(symbol); };
        if (variant === 'bar') {
          return (
            <button
              key={symbol}
              type="button"
              className="global-app-bar__rec"
              data-testid="status-chip-recording"
              data-symbol={symbol}
              title={title}
              aria-label={`${RECORDING_CHIP_ROLE} ${value}`}
              onClick={open}
            >
              <span className="dot recording" aria-hidden="true" />
              <span className="global-app-bar__rec-role">{RECORDING_CHIP_ROLE}</span>
              <span className="global-app-bar__rec-symbol">{symbol}</span>
              <span className="global-app-bar__rec-time">{elapsedClockLabel(segmentMs)}</span>
            </button>
          );
        }
        return (
          <button
            key={symbol}
            type="button"
            className="status-chip status-chip--compact status-chip--recording"
            data-testid="status-chip-recording"
            data-symbol={symbol}
            title={title}
            aria-label={`${RECORDING_CHIP_ROLE} ${value}`}
            onClick={open}
          >
            <span className="dot recording" />
            <Disc className="status-chip__icon" aria-hidden="true" />
            <span className="status-chip__role">{RECORDING_CHIP_ROLE}</span>
            <span className="status-chip__value">{value}</span>
          </button>
        );
      })}
    </>
  );
}
