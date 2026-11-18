/**
 * Whether the phone's Time & Sales is live, said over its rows (operator report 2026-11-17: "the time and sale
 * was not moving, so there was a missing piece").
 *
 * A tape with no new row is one of several things, and they used to look the same: the stock did not trade, the
 * line at IBKR is down, the socket to the PC went quiet, or the screen is still connecting. The line here always
 * says which. The phone judges nothing: each word is the socket's own state (`useIbkrTape`) or the backend's
 * reading of the line (`ibkr/tapeSilence`, the desk's own badge), and the count is the desk's clock.
 */
import { useEffect, useState } from 'react';
import { TAPE_STATUS_LIVE } from '../../constantGroups/features';
import {
  TAPE_STATUS_CONNECTING,
  TAPE_STATUS_ERROR,
  TAPE_STATUS_NO_DATA,
  TAPE_STATUS_NO_LANE,
  TAPE_STATUS_RETRYING,
  TAPE_LAST_PRINT_SHOW_MS,
  TAPE_NO_DATA_NOTE,
} from '../../constantGroups/market_ui';
import { tapeSilenceBadge } from '../../ibkr/tapeSilence';
import type { TapeState } from '../../ibkr/tapeFeed';
import { deskNow } from '../../utils/deskClock';

export interface TapeStatusView {
  /** The word: LIVE, QUIET 45s, LINE DOWN 45s, NO DATA 6s, CONNECTING ... */
  label: string;
  tone: 'good' | 'quiet' | 'warn' | 'bad';
  /** Beside a live word: how old the newest print is ("last 23s"); null when it is fresh or there is none. */
  age: string | null;
  /** Why the tape is not live, or a halt's line, in the desk's words; written under the rows. */
  note: string | null;
  /** False while what is on the rows may be old: they are drawn faded. */
  live: boolean;
}

function count(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return s < 100 ? `${s}s` : `${Math.floor(s / 60)}m`;
}

/** The tape's word at `nowMs` (the desk's clock). Pure. */
export function tapeStatus(tape: TapeState, nowMs: number): TapeStatusView {
  if (tape.laneWait) {
    return { label: TAPE_STATUS_NO_LANE, tone: 'quiet', age: null, note: tape.laneWait.plain, live: false };
  }
  if (tape.quietSince != null) {
    const label = `${TAPE_STATUS_NO_DATA} ${count(nowMs - tape.quietSince)}`;
    return { label, tone: 'bad', age: null, note: TAPE_NO_DATA_NOTE, live: false };
  }
  if (tape.error) {
    const retrying = tape.retryAt != null;
    return {
      label: retrying ? TAPE_STATUS_RETRYING : TAPE_STATUS_ERROR, tone: retrying ? 'warn' : 'bad', age: null,
      note: tape.error, live: false,
    };
  }
  if (!tape.connected) {
    return { label: TAPE_STATUS_CONNECTING, tone: 'quiet', age: null, note: null, live: false };
  }
  const silence = tapeSilenceBadge(tape.silence, nowMs);
  if (silence) {
    // A dead line, or one that may be: the rows are not the market. A halt or a quiet name is a live tape.
    const down = tape.silence?.state === 'dead' || tape.silence?.state === 'silent';
    return { label: silence.label, tone: silence.tone, age: null, note: down ? silence.notice : null, live: !down };
  }
  const newest = tape.prints[0] ? Date.parse(tape.prints[0].time) : Number.NaN;
  const old = Number.isFinite(newest) ? nowMs - newest : 0;
  return {
    label: TAPE_STATUS_LIVE, tone: 'good', age: old >= TAPE_LAST_PRINT_SHOW_MS ? `last ${count(old)}` : null,
    note: null, live: true,
  };
}

/** `tapeStatus`, re-read once a second on the desk's clock. */
export function useTapeStatus(tape: TapeState): TapeStatusView {
  const [nowMs, setNowMs] = useState(() => deskNow());
  useEffect(() => {
    setNowMs(deskNow());
    const id = window.setInterval(() => setNowMs(deskNow()), 1_000);
    return () => window.clearInterval(id);
  }, []);
  return tapeStatus(tape, nowMs);
}

export function TapeStatusLine({ status }: { status: TapeStatusView }) {
  return (
    <div className="ph-tape__status" role="status" data-testid="phone-tape-status" data-tone={status.tone}>
      <b><i aria-hidden="true" />{status.label}</b>
      {status.age ? <span>{status.age}</span> : null}
    </div>
  );
}
