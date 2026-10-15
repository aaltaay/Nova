/**
 * What records now, on top of Records (operator ask 2026-10-14: "i need a way
 * to turn off the recording"). Each live Session Record says who started it --
 * auto-record (its setup and why) or you -- how long it has run, its counts and
 * a timeline from its first start to now, with Open in Trader and a held Stop.
 * Hold to stop all ends every one. With nothing recording, the card says why
 * nothing will start and offers the door that would.
 */
import { useState } from 'react';
import { captureStopHoldLabel, HoldToStopButton, startTabRecord, stopAllRecords, stopTabRecord } from '../../capture';
import { AUTO_RECORD_WHY_WORDS, recordingChipHolding } from '../../capture/constants';
import { elapsedClockLabel, recordingView } from '../../capture/recordingSignalModel';
import { NAV_RAIL_RECORDING_MAX } from '../../constantGroups/nav_rail';
import type { IbkrClientStatus } from '../../ibkr/ibkrStatusPoller';
import { setupLabel } from '../../setups';
import type { CaptureSessionRow } from '../../sim/useSimSessionController';
import { whyProps } from '../../ux/whyTip';
import {
  RECORDS_AUTO_BUSY,
  RECORDS_AUTO_FAILED,
  RECORDS_AUTO_RECORD,
  RECORDS_FREE_AUTO_OFF,
  RECORDS_FREE_AUTO_ON,
  RECORDS_FREE_SLOT,
  RECORDS_NOT_RECORDING_TITLE,
  RECORDS_NOTHING_AUTO_ON,
  RECORDS_NOW_TITLE,
  RECORDS_OPEN_TRADER,
  RECORDS_RECORD_A_SYMBOL,
  RECORDS_RECORD_BUSY,
  RECORDS_RECORD_CANCEL,
  RECORDS_RECORD_FAILED,
  RECORDS_RECORD_NEEDS_SYMBOL,
  RECORDS_RECORD_START,
  RECORDS_RECORD_SYMBOL_PLACEHOLDER,
  RECORDS_RESUMED_AFTER,
  RECORDS_STARTED_BY_YOU,
  RECORDS_STOP,
  RECORDS_STOP_ALL,
  RECORDS_STOP_ALL_LABEL,
  RECORDS_STOP_FAILED,
  RECORDS_TAG_AUTO,
  RECORDS_TAG_YOU,
  RECORDS_TURN_AUTO_ON,
  recordsNothingAutoOff,
  recordsSegmentLine,
  recordsSlotsInUse,
} from './recordsConstants';
import { etClock, hm, etMinute, todayEasternDate } from './recordsModel';
import type { AutoRecordSwitchControl } from './useAutoRecordSwitch';
import { TickerLink } from '../../components/TickerLink';

interface Props {
  status: IbkrClientStatus;
  /** Fresh recording symbols only (`useRecordingSymbols`). */
  symbols: readonly string[];
  /** Today's listing rows by symbol: their spans draw each timeline. */
  todayRows: ReadonlyMap<string, CaptureSessionRow>;
  nowMs: number;
  onOpenTrader: (symbol: string) => void;
  control: AutoRecordSwitchControl;
}

const isoSec = (iso: string | null | undefined): number | null => {
  const ms = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(ms) ? ms / 1000 : null;
};

/** Who started it and why, in one line. */
function whoLine(auto: boolean, setup: string | null, why: string | null): string {
  if (!auto) return RECORDS_STARTED_BY_YOU;
  const parts = [RECORDS_AUTO_RECORD];
  if (setup) parts.push(setupLabel(setup));
  if (why) parts.push(AUTO_RECORD_WHY_WORDS[why] ?? why);
  return parts.join(' · ');
}

/** This recording alone, from its first start to now: amber where a later segment began. */
function MiniTimeline({ spans, nowSec, startLabel, breakLabel }: {
  spans: number[][]; nowSec: number; startLabel: string; breakLabel: string | null;
}) {
  const a0 = spans[0][0] - 4;
  const a1 = nowSec + 2;
  const q = (t: number) => `${((Math.max(a0, Math.min(a1, t)) - a0) / (a1 - a0)) * 100}%`;
  const last = spans.length - 1;
  return (
    <div>
      <div className="records-mini">
        {spans.map(([a, b], i) => {
          const end = i === last ? Math.max(b, nowSec) : b;
          return <div key={a} className={`records-cov__span${i === last ? ' is-live' : ''}`}
            style={{ left: q(a), width: `max(2px, calc(${q(end)} - ${q(a)}))` }} />;
        })}
        {spans.slice(1).map(([a]) => <div key={`r${a}`} className="records-mini__break" style={{ left: q(a) }} />)}
        <div className="records-cov__now" style={{ left: q(nowSec) }} />
      </div>
      <div className="records-mini__axis">
        <span>{startLabel}</span>{breakLabel && <span className="records-warn">{breakLabel}</span>}<span>now</span>
      </div>
    </div>
  );
}

export function RecordingNowCard({ status, symbols, todayRows, nowMs, onOpenTrader, control }: Props) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [allError, setAllError] = useState<string | null>(null);
  const auto = status.auto_record;
  const sw = auto?.switch;
  const autoOn = sw?.mode === 'on';
  const nowSec = nowMs / 1000;
  const used = symbols.length;
  const free = Math.max(0, NAV_RAIL_RECORDING_MAX - used);

  const stop = async (symbol: string) => {
    const error = await stopTabRecord(symbol);
    setErrors(prev => {
      const next = { ...prev };
      if (error) next[symbol] = error; else delete next[symbol];
      return next;
    });
  };
  const stopAll = async () => setAllError(await stopAllRecords());

  if (!used) {
    const offUntil = sw?.until != null ? `${hm(etMinute(sw.until))} ET${
      todayEasternDate(new Date(sw.until * 1000)) === todayEasternDate(new Date(nowMs)) ? '' : ' tomorrow'}` : null;
    const canTurnOn = sw != null && sw.source !== 'env' && sw.mode !== 'on';
    return (
      <section className="records-card records-now is-idle" aria-label={RECORDS_NOT_RECORDING_TITLE} data-testid="records-now">
        <header className="records-card__head">
          <span className="records-idle-dot" aria-hidden="true" />
          <h3 className="records-card__title">{RECORDS_NOT_RECORDING_TITLE}</h3>
          <span className="records-card__sub">{recordsSlotsInUse(0, NAV_RAIL_RECORDING_MAX)}</span>
        </header>
        <div className="records-now__idle">
          <p>{sw && sw.mode !== 'on' ? recordsNothingAutoOff(sw.mode, offUntil) : RECORDS_NOTHING_AUTO_ON}</p>
          <div className="records-now__acts">
            {canTurnOn && (
              <button type="button" className="records-btn" disabled={control.busy != null}
                {...whyProps(control.busy != null, RECORDS_AUTO_BUSY)} data-testid="records-auto-on-now"
                onClick={() => void control.setMode('on')}>
                {RECORDS_TURN_AUTO_ON}
              </button>
            )}
            <RecordASymbol />
          </div>
          {canTurnOn && control.error && (
            <p className="records-warn" role="alert">{RECORDS_AUTO_FAILED} {control.error}</p>
          )}
        </div>
      </section>
    );
  }

  return (
    <section className="records-card records-now is-live" aria-label={RECORDS_NOW_TITLE} data-testid="records-now">
      <header className="records-card__head">
        <span className="records-pulse" aria-hidden="true" />
        <h3 className="records-card__title">{RECORDS_NOW_TITLE}</h3>
        <span className="records-card__sub">{recordsSlotsInUse(used, NAV_RAIL_RECORDING_MAX)}</span>
        {used > 1 && (
          <HoldToStopButton role="button" label={RECORDS_STOP_ALL_LABEL} onConfirm={() => void stopAll()}
            className="records-btn records-btn--stop records-now__all" testId="records-stop-all">
            <span className="records-btn__sq" aria-hidden="true" />{RECORDS_STOP_ALL}
          </HoldToStopButton>
        )}
      </header>
      {allError && <p className="records-now__error records-bad" role="alert">{RECORDS_STOP_FAILED} {allError}</p>}
      {symbols.map(symbol => {
        const view = recordingView(status, symbol, nowMs);
        const session = (status.capture_sessions ?? []).find(row => row.symbol === symbol);
        const row = todayRows.get(symbol);
        const isAuto = (auto?.symbols ?? []).includes(symbol);
        const started = isoSec(session?.started_et);
        const segStarted = isoSec(session?.segment_started_et);
        const resumed = (view?.segment ?? 1) > 1 && segStarted != null;
        const spans = row?.spans?.length ? row.spans : started != null ? [[started, nowSec]] : [];
        return (
          <div key={symbol} className="records-now__row" data-testid={`records-now-${symbol}`}>
            <div className="records-now__sym">
              <span className="records-pulse" aria-hidden="true" /><TickerLink symbol={symbol} look="own" />
              <span className={`records-tag ${isAuto ? 'is-auto' : 'is-you'}`}>{isAuto ? RECORDS_TAG_AUTO : RECORDS_TAG_YOU}</span>
            </div>
            <div className="records-now__who">
              <div className="records-now__why">{whoLine(isAuto, auto?.setup?.[symbol] ?? null, auto?.why?.[symbol] ?? null)}</div>
              <div className="records-now__line">
                {recordsSegmentLine({
                  elapsed: elapsedClockLabel(view?.segmentSinceMs ?? view?.sinceMs ?? null),
                  since: started != null ? etClock(started) : null,
                  resumedAt: resumed && segStarted != null ? etClock(segStarted) : null,
                  resumedWhy: row?.last_reason ? RECORDS_RESUMED_AFTER[row.last_reason] ?? null : null,
                  prints: view?.prints ?? 0,
                  l2: view?.l2 ?? 0,
                })}
              </div>
              {errors[symbol] && <div className="records-bad" role="alert">{RECORDS_STOP_FAILED} {errors[symbol]}</div>}
            </div>
            {spans.length > 0 ? (
              <MiniTimeline spans={spans} nowSec={nowSec} startLabel={etClock(spans[0][0])}
                breakLabel={resumed && segStarted != null ? `resumed ${etClock(segStarted)}` : null} />
            ) : <div />}
            <div className="records-now__acts">
              <button type="button" className="records-btn records-btn--ghost" data-testid={`records-now-open-${symbol}`}
                onClick={() => onOpenTrader(symbol)}>
                {RECORDS_OPEN_TRADER}
              </button>
              <HoldToStopButton role="button" label={captureStopHoldLabel(symbol)} onConfirm={() => void stop(symbol)}
                className="records-btn records-btn--stop" testId={`records-now-stop-${symbol}`}
                holding={<><span className="records-btn__sq" aria-hidden="true" />{recordingChipHolding(symbol)}</>}>
                <span className="records-btn__sq" aria-hidden="true" />{RECORDS_STOP}
              </HoldToStopButton>
            </div>
          </div>
        );
      })}
      {free > 0 && (
        <div className="records-now__free" data-testid="records-now-free">
          <span className="records-now__slot">{free === 1 ? RECORDS_FREE_SLOT : `${free} free slots`}</span>
          {autoOn ? RECORDS_FREE_AUTO_ON : RECORDS_FREE_AUTO_OFF}
        </div>
      )}
    </section>
  );
}

/** Record a symbol from Records: the same door as a Trader tab's Record (`POST /api/capture`). */
function RecordASymbol() {
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!open) {
    return (
      <button type="button" className="records-btn records-btn--ghost" data-testid="records-record-symbol"
        onClick={() => setOpen(true)}>
        {RECORDS_RECORD_A_SYMBOL}
      </button>
    );
  }
  const start = async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    setBusy(true);
    const failed = await startTabRecord(sym);
    setBusy(false);
    setError(failed);
    if (!failed) { setOpen(false); setSymbol(''); }
  };
  return (
    <form className="records-now__record" onSubmit={e => { e.preventDefault(); void start(); }}>
      <input className="records-input" value={symbol} autoFocus placeholder={RECORDS_RECORD_SYMBOL_PLACEHOLDER}
        aria-label={RECORDS_RECORD_SYMBOL_PLACEHOLDER} data-testid="records-record-input"
        onChange={e => setSymbol(e.target.value.toUpperCase())} />
      <button type="submit" className="records-btn" disabled={busy || !symbol.trim()} data-testid="records-record-start"
        {...whyProps(busy || !symbol.trim(), busy ? RECORDS_RECORD_BUSY : RECORDS_RECORD_NEEDS_SYMBOL)}>
        {RECORDS_RECORD_START}
      </button>
      <button type="button" className="records-btn records-btn--ghost" onClick={() => { setOpen(false); setError(null); }}>
        {RECORDS_RECORD_CANCEL}
      </button>
      {error && <span className="records-bad" role="alert">{RECORDS_RECORD_FAILED} {error}</span>}
    </form>
  );
}
