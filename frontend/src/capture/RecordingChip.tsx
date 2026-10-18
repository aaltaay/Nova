/**
 * Header REC chips: one per recording symbol (up to three), none otherwise.
 * Red dot, symbol and elapsed time; the hover card carries the counts, who
 * started it, and a held Stop with a way to Records, so any page can stop a
 * recording (operator ask 2026-10-14). Click opens that tab. `variant="bar"` is the redesigned global bar's chip
 * (`● REC GRML 5:12`, words on screen); the default stays the compact
 * icon chip the status cluster uses.
 *
 * The card counts up every tick, so it is a rendered Radix tooltip updated in
 * place -- a native `title` that changes each second makes the browser drop
 * and redraw its tooltip, which flickered under the pointer.
 */
import { Disc } from 'lucide-react';
import { Tooltip } from 'radix-ui';
import { useEffect, useState, useSyncExternalStore } from 'react';
import { BOT_SETUP_LABELS } from '../constantGroups/bot';
import { getIbkrStatusSnapshot } from '../ibkr';
import type { AutoRecordStatus } from '../ibkr';
import {
  AUTO_RECORD_WHY_WORDS,
  captureStopHoldLabel,
  RECORDING_CHIP_RECORDS,
  RECORDING_CHIP_ROLE,
  RECORDING_CHIP_STOP,
  RECORDING_CHIP_STOP_FAILED,
  RECORDING_CHIP_TOOLTIP_DELAY_MS,
  RECORDING_SIGNAL_TICK_MS,
  recordingChipHolding,
  recordingChipTitle,
  recordingChipValue,
} from './constants';
import { HoldToStopButton } from './HoldToStopButton';
import { elapsedClockLabel, elapsedLabel, recordingView } from './recordingSignalModel';
import { AUTO_RECORD_CHIP_LINE } from '../leaderboard';
import { getRecordingSymbols, getSessionRecordVersion, stopTabRecord, subscribeSessionRecord } from './sessionRecordStore';
import './recordingSignal.css';

interface Props {
  onOpenSymbol?: (symbol: string) => void;
  /** Opens Records; the card's Records button shows only when given. */
  onOpenRecords?: () => void;
  variant?: 'compact' | 'bar';
}

/** "5-minute flat top · near its trigger" for an auto-recorded symbol; null when Nova does not say. */
function autoWhyLine(auto: AutoRecordStatus | null | undefined, symbol: string): string | null {
  const setup = auto?.setup?.[symbol];
  const why = auto?.why?.[symbol];
  const parts = [setup ? BOT_SETUP_LABELS[setup] ?? setup : null, why ? AUTO_RECORD_WHY_WORDS[why] ?? why : null];
  return parts.filter(Boolean).join(' · ') || null;
}

/** The card's held Stop and the way to Records; a Stop that fails says so on the card. */
function CardActions({ symbol, onOpenRecords }: { symbol: string; onOpenRecords?: () => void }) {
  const [error, setError] = useState<string | null>(null);
  return (
    <>
      <div className="recording-chip-tip__acts">
        <HoldToStopButton role="button" label={captureStopHoldLabel(symbol)}
          onConfirm={() => void stopTabRecord(symbol).then(setError)} className="recording-chip-tip__stop"
          testId="status-chip-recording-stop"
          holding={<><span className="recording-chip-tip__sq" aria-hidden="true" />{recordingChipHolding(symbol)}</>}>
          <span className="recording-chip-tip__sq" aria-hidden="true" />{RECORDING_CHIP_STOP}
        </HoldToStopButton>
        {onOpenRecords && (
          <button type="button" className="recording-chip-tip__btn" data-testid="status-chip-recording-records"
            onClick={onOpenRecords}>
            {RECORDING_CHIP_RECORDS}
          </button>
        )}
      </div>
      {error && <div className="recording-chip-tip__error" role="alert">{RECORDING_CHIP_STOP_FAILED} {error}</div>}
    </>
  );
}

export function RecordingChip({ onOpenSymbol, onOpenRecords, variant = 'compact' }: Props) {
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
    <Tooltip.Provider delayDuration={RECORDING_CHIP_TOOLTIP_DELAY_MS}>
      {symbols.map((symbol) => {
        const view = recordingView(status, symbol, now);
        // "For how long" is this segment: after a resume the session began earlier
        // than the recording has actually been running, and the card says both.
        const segmentMs = view?.segmentSinceMs ?? view?.sinceMs ?? null;
        const elapsed = elapsedLabel(segmentMs);
        const value = recordingChipValue(symbol, elapsed);
        // Auto-record stays quiet (ADR 023): its symbols are marked "auto" in the card, nowhere else.
        const auto = (status.auto_record?.symbols ?? []).includes(symbol);
        const card = view
          ? recordingChipTitle({
            ...view, elapsed, sessionElapsed: elapsedLabel(view.sinceMs), auto, autoWhy: autoWhyLine(status.auto_record, symbol),
          })
          : `Recording ${symbol}${auto ? ` (${AUTO_RECORD_CHIP_LINE})` : ''}`;
        const open = (e: React.MouseEvent) => { e.preventDefault(); onOpenSymbol?.(symbol); };
        const chip = variant === 'bar' ? (
          <button
            type="button"
            className="global-app-bar__rec"
            data-testid="status-chip-recording"
            data-symbol={symbol}
            aria-label={`${RECORDING_CHIP_ROLE} ${value}`}
            onClick={open}
          >
            <span className="dot recording" aria-hidden="true" />
            <span className="global-app-bar__rec-role">{RECORDING_CHIP_ROLE}</span>
            <span className="global-app-bar__rec-symbol">{symbol}</span>
            <span className="global-app-bar__rec-time">{elapsedClockLabel(segmentMs)}</span>
          </button>
        ) : (
          <button
            type="button"
            className="status-chip status-chip--compact status-chip--recording"
            data-testid="status-chip-recording"
            data-symbol={symbol}
            aria-label={`${RECORDING_CHIP_ROLE} ${value}`}
            onClick={open}
          >
            <span className="dot recording" />
            <Disc className="status-chip__icon" aria-hidden="true" />
            <span className="status-chip__role">{RECORDING_CHIP_ROLE}</span>
            <span className="status-chip__value">{value}</span>
          </button>
        );
        return (
          <Tooltip.Root key={symbol}>
            <Tooltip.Trigger asChild>{chip}</Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                className="recording-chip-tip"
                side="bottom"
                align="start"
                sideOffset={6}
                collisionPadding={8}
                data-testid="status-chip-recording-tip"
                data-symbol={symbol}
              >
                {card.split('\n').map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
                <CardActions symbol={symbol} onOpenRecords={onOpenRecords} />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        );
      })}
    </Tooltip.Provider>
  );
}
