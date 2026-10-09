/**
 * Time & Sales says when its live line stopped printing (#722), so a frozen tape never reads LIVE.
 *
 * 2026-10-05 09:35:42 ET: SAIQ's tape stopped while its Level 2 kept updating, with no word from IBKR,
 * and the pane sat on its last print under LIVE for about six minutes. The backend now reads the
 * line's silence on each idle ping (`ibkr/tape_silence.py`); this turns it into the badge and a short
 * line above the rows (the rail's tape column is narrow), with the backend's full words on hover.
 * The badge counts the seconds on the desk's clock; any print clears it. LINE DOWN (red) is the
 * backend's proof that the line is dead, not quiet: the stock's Level 1 counted trades it never printed.
 */
import { useEffect, useState } from 'react';
import {
  TAPE_SILENCE_DEAD_NOTICE,
  TAPE_SILENCE_HALTED_NOTICE,
  TAPE_SILENCE_SILENT_NOTICE,
  TAPE_STATUS_DEAD,
  TAPE_STATUS_HALTED,
  TAPE_STATUS_QUIET,
  TAPE_STATUS_SILENT,
} from '../constantGroups/market_ui';
import type { TapeSilence } from './tapeFeed';
import { fmtTapeTime } from './TapeRow';

export interface TapeSilenceBadge {
  label: string;
  /** The backend's full words, for the badge's and the line's hover. */
  title: string;
  /** Red for a dead line, amber for a halt or a line that may be down, grey for a quiet name. */
  tone: 'bad' | 'warn' | 'quiet';
  /** A short line above the rows for a dead line, a halt or a line that may be down; none for a quiet name. */
  notice: string | null;
}

export function tapeSilenceBadge(silence: TapeSilence | null | undefined, nowMs: number): TapeSilenceBadge | null {
  if (!silence) return null;
  const secs = Math.max(0, Math.floor(nowMs / 1000 - silence.since));
  if (silence.state === 'halted') {
    return { label: TAPE_STATUS_HALTED, title: silence.text, tone: 'warn', notice: TAPE_SILENCE_HALTED_NOTICE };
  }
  if (silence.state === 'dead' || silence.state === 'silent') {
    const since = fmtTapeTime(new Date(silence.since * 1000).toISOString());
    const dead = silence.state === 'dead';
    return {
      label: `${dead ? TAPE_STATUS_DEAD : TAPE_STATUS_SILENT} ${secs}s`,
      title: silence.text,
      tone: dead ? 'bad' : 'warn',
      notice: (dead ? TAPE_SILENCE_DEAD_NOTICE : TAPE_SILENCE_SILENT_NOTICE).replace('{since}', since),
    };
  }
  return { label: `${TAPE_STATUS_QUIET} ${secs}s`, title: silence.text, tone: 'quiet', notice: null };
}

/** The desk's clock, once a second while `active` (the badge's count); otherwise left alone. */
export function useSecondsTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}
