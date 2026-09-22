/**
 * Pure helpers for the strip scrubber: clock text, the playhead tag, and the
 * band's segments (recorded / gap / downloaded / failed) as fractions of the
 * 04:00-20:00 session. Nothing here reads the DOM or a store.
 */
import { simStripFailedTitle } from '../constantGroups/trader_chrome';
import { SIM_ET_TIME_ZONE, SIM_SESSION_MINUTES, SIM_SESSION_OPEN_LABEL, simCaptureGapTitle } from './simConstants';
import { captureBandSegments, coverageRanges } from './simCoverage';
import type { HistoricalSelection } from './historicalTypes';
import type { SimClockState } from './simClockTypes';

export function formatClock(iso?: string | null): string {
  if (!iso) return '--:--:--';
  try {
    return new Date(iso).toLocaleTimeString('en-US', {
      timeZone: SIM_ET_TIME_ZONE, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch {
    return '--:--:--';
  }
}

/** "HH:MM:00" for a minute offset from the session open ("04:00" -> minutes). */
export function formatMinuteClock(minuteFromOpen: number, openingLabel: string = SIM_SESSION_OPEN_LABEL): string {
  const opening = Number(openingLabel.slice(0, 2)) * 60 + Number(openingLabel.slice(3, 5));
  const total = Math.max(0, Math.floor(minuteFromOpen)) + opening;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`;
}

/** "Sep 21" from the clock's Eastern session date. */
export function formatShortDate(iso?: string | null): string {
  if (!iso) return '';
  try {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

/** Today's Eastern date as YYYY-MM-DD. */
export function todayEt(now: Date = new Date()): string {
  try {
    return now.toLocaleDateString('en-CA', { timeZone: SIM_ET_TIME_ZONE });
  } catch {
    return now.toISOString().slice(0, 10);
  }
}

export function sessionOpeningLabel(clock: SimClockState | null | undefined): string {
  return clock?.session_open_et ? formatClock(clock.session_open_et).slice(0, 5) : SIM_SESSION_OPEN_LABEL;
}

/**
 * The tag riding above the playhead OFF the live edge: the playhead time, plus
 * the date only when the session is not today. At the edge the global bar
 * clock is the truth, so the tag is empty.
 */
export function playheadTag(
  clock: SimClockState | null | undefined,
  dragMinute: number | null,
  today: string = todayEt(),
): string {
  if (!clock || clock.live_edge) return '';
  const time = dragMinute != null
    ? formatMinuteClock(dragMinute, sessionOpeningLabel(clock))
    : formatClock(clock.sim_time_et);
  const date = clock.session_date ?? clock.session_open_et?.slice(0, 10) ?? null;
  return date && date !== today ? `${time} · ${formatShortDate(date)}` : time;
}

export interface StripBandSegment {
  left: number;
  width: number;
  kind: 'recorded' | 'gap' | 'downloaded' | 'failed';
  title: string;
}

function epoch(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms / 1000 : null;
}

/** Session minute (from the open) of an epoch second; null when the clock has no session bounds. */
export function sessionMinuteOf(epochSeconds: number, clock: SimClockState | null | undefined): number | null {
  const open = epoch(clock?.session_open_et);
  if (open == null) return null;
  return Math.max(0, Math.round((epochSeconds - open) / 60));
}

/**
 * What the band draws for the loaded replay. A capture: its recorded stretches
 * and the gaps between them (`captureBandSegments`). A historical window: the
 * downloaded ranges against the session. A failed replay: one red stretch
 * across the band that names the error. Nothing loaded: nothing.
 */
export function stripBandSegments(
  clock: SimClockState | null | undefined,
  selection: HistoricalSelection | null | undefined,
  format: (epochSeconds: number) => string,
): StripBandSegment[] {
  if (!clock) return [];
  if (clock.replay_ok === false) {
    return [{ left: 0, width: 1, kind: 'failed', title: simStripFailedTitle(clock.replay_error || 'replay failed') }];
  }
  if (clock.replay_source === 'capture') {
    return captureBandSegments(clock).map(segment => ({
      left: segment.left,
      width: segment.width,
      kind: segment.kind,
      title: segment.kind === 'gap' ? simCaptureGapTitle(segment.reason) : 'Recorded',
    }));
  }
  if (clock.replay_source === 'historical' && selection) {
    const open = epoch(clock.session_open_et);
    const close = epoch(clock.session_close_et);
    if (open == null || close == null || close <= open) return [];
    return coverageRanges(selection)
      .map(([a, b]) => ({
        left: (Math.max(a, open) - open) / (close - open),
        width: (Math.min(b, close) - Math.max(a, open)) / (close - open),
        kind: 'downloaded' as const,
        title: `Trades downloaded ${format(a)}–${format(b)} ET`,
      }))
      .filter(segment => segment.width > 0);
  }
  return [];
}

/** First recorded / downloaded session minute, for the ⏮ transport; 0 when nothing is loaded. */
export function firstReplayMinute(
  clock: SimClockState | null | undefined,
  selection: HistoricalSelection | null | undefined,
): number {
  const max = clock?.minute_max ?? SIM_SESSION_MINUTES;
  if (clock?.replay_source === 'capture') {
    const first = captureBandSegments(clock).find(segment => segment.kind === 'recorded');
    return first ? Math.round(first.left * max) : 0;
  }
  if (clock?.replay_source === 'historical' && selection?.start_ts != null) {
    return sessionMinuteOf(selection.start_ts, clock) ?? 0;
  }
  return 0;
}
