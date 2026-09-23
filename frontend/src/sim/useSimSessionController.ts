import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { replayPollResource } from './replayPollResource';
import { simClockResource } from './simClockResource';
import { CAPTURE_REPLAY_FAILURE, publishReplayReply } from './captureReplayLoad';
import { useReplayActions } from './useReplayActions';
import { emitSimClockScrub, SIM_CLOCK_SCRUB_EVENT, SIM_SEEK_CANCEL_EVENT, type SimClockScrubDetail } from './simClockEvents';
import { SIM_CAPTURE_POLL_MS, SIM_SCRUB_KEYBOARD_MS } from './simConstants';
import type { SimClockState } from './simClockTypes';
import { parseCaptureSessions } from './captureSessionsParse';
import { SIM_DAY_PICKER_FAILED } from '../leaderboard/leaderboardConstants';
/** One Session Record row of `GET /api/capture/sessions`, as parsed at the boundary. */
export interface CaptureSessionRow {
  symbol: string;
  /** Rows recorded; null when Nova has not counted them (the backend's `-1`) or does not know. */
  prints: number | null;
  l2: number | null;
  usable?: boolean; empty?: boolean; unavailable_reason?: string | null;
  segments?: number; missing_sec?: number; last_reason?: string | null; status?: string;
  /** Who recorded it: `ibkr` for Session Record; anything else is not a real recording (ADR 019). */
  source?: string | null;
  /** `[[start, stop], ...]` whole epoch seconds per recorded segment (open: runs to now). */
  spans?: number[][];
}
export interface CaptureSessions {
  days: { date: string; ticker_count: number }[];
  tickers_by_day: Record<string, CaptureSessionRow[]>;
}
const clockResource = simClockResource;
export const capturesResource = replayPollResource<CaptureSessions>(
  '/api/capture/sessions', () => SIM_CAPTURE_POLL_MS, { parse: parseCaptureSessions },
);
/**
 * ``activeSymbol`` is the tab the operator is looking at. It rides on every scrub so a
 * move off the live edge with nothing loaded can select that tab's Session
 * Record for today underneath the playhead (ADR 020 live-edge amendment); the
 * backend cannot see UI tabs. Omitted when the desk has no active tab.
 */
export function useSimSessionController(active: boolean, openStockView: (symbol: string) => void, activeSymbol?: string | null) {
  const subscribeClock = useCallback((listener: () => void) => active ? clockResource.subscribe(listener) : () => {}, [active]);
  const subscribeCaptures = useCallback((listener: () => void) => active ? capturesResource.subscribe(listener) : () => {}, [active]);
  const clockState = useSyncExternalStore(subscribeClock, clockResource.getSnapshot);
  const captureState = useSyncExternalStore(subscribeCaptures, capturesResource.getSnapshot);
  const clock = active ? clockState.data : null;
  const [day, setDay] = useState('');
  const [symbol, setSymbol] = useState('');
  const [dragMinute, setDragMinute] = useState<number | null>(null);
  const dragging = useRef(false);
  const seekRunning = useRef(false);
  const seekPending = useRef<number | null>(null);
  const sessionActive = useRef(active);
  const timer = useRef<number | undefined>(undefined);
  const { request, busy, errors } = useReplayActions();
  const clearSeekIntent = useCallback(() => {
    window.clearTimeout(timer.current); timer.current = undefined;
    seekPending.current = null; dragging.current = false; setDragMinute(null);
  }, []);
  useEffect(() => {
    if (clock?.replay_source === 'capture' && clock.replay_date && clock.replay_symbol) {
      setDay(clock.replay_date); setSymbol(clock.replay_symbol);
    }
  }, [clock]);
  useEffect(() => {
    sessionActive.current = active;
    if (!active) return;
    const onSelection = (event: Event) => {
      const detail = (event as CustomEvent<SimClockScrubDetail | undefined>).detail;
      if (detail?.minute == null) { clearSeekIntent(); clockResource.invalidate(clockResource.getSnapshot().data); }
    };
    window.addEventListener(SIM_CLOCK_SCRUB_EVENT, onSelection);
    window.addEventListener(SIM_SEEK_CANCEL_EVENT, clearSeekIntent);
    return () => { sessionActive.current = false; seekPending.current = null; window.removeEventListener(SIM_CLOCK_SCRUB_EVENT, onSelection); window.removeEventListener(SIM_SEEK_CANCEL_EVENT, clearSeekIntent); window.clearTimeout(timer.current); };
  }, [active, clearSeekIntent]);
  const setClock = (value: SimClockState) => { clockResource.suspend(); clockResource.setData(value); };
  const tabSymbol = activeSymbol?.trim().toUpperCase() || null;
  const postClock = useCallback(async (body: object, key = 'clock', failure = 'Could not change Sim time') => {
    clockResource.suspend();
    const next = await request<SimClockState>(key, '/clock', body, failure);
    if (next) {
      clockResource.suspend();
      clockResource.setData(next);
      // Read back the parsed clock: the reply is raw JSON until it passes the boundary.
      const parsed = clockResource.getSnapshot().data;
      emitSimClockScrub({ symbol: parsed?.replay_symbol ?? undefined, minute: parsed?.minute_from_open ?? 0 });
    }
    clockResource.resume();
    return next;
  }, [request]);
  const commit = async (minute: number) => {
    window.clearTimeout(timer.current);
    timer.current = undefined;
    dragging.current = false;
    setDragMinute(minute);
    seekPending.current = minute;
    if (seekRunning.current) return;
    seekRunning.current = true;
    try {
      // Keep the focused range usable while a POST is pending. Intermediate key
      // steps coalesce, but the final requested playhead is always committed.
      while (seekPending.current != null && sessionActive.current) {
        const requested = seekPending.current;
        seekPending.current = null;
        await postClock(tabSymbol ? { minute_from_open: requested, symbol: tabSymbol } : { minute_from_open: requested });
      }
    } finally {
      seekRunning.current = false;
      if (sessionActive.current && timer.current == null && !dragging.current) setDragMinute(null);
    }
  };
  const onScrubInput = (minute: number) => {
    setDragMinute(minute);
    window.clearTimeout(timer.current);
    // Pointer drags are local until release. Keyboard steps debounce into one seek.
    if (!dragging.current) timer.current = window.setTimeout(() => void commit(minute), SIM_SCRUB_KEYBOARD_MS);
  };
  const beginDrag = () => { dragging.current = true; clockResource.suspend(); };
  const onFollowWall = async () => { clearSeekIntent(); await postClock({ follow_wall: true }, 'follow'); };
  /** Move Sim to a day (nothing loaded, parked at 07:00 ET); null returns to today (ADR 023). */
  const jumpToDay = async (date: string | null) => {
    clearSeekIntent();
    await postClock({ session_date: date }, 'day', SIM_DAY_PICKER_FAILED);
  };
  /** Seek to an exact second from the open (the slider is minute-grained; ⏮ is not, R22). */
  const seekToSecond = async (second: number) => {
    clearSeekIntent();
    await postClock(tabSymbol ? { second_from_open: second, symbol: tabSymbol } : { second_from_open: second });
  };
  const applyReplay = async (nextDay: string, nextSymbol: string) => {
    clearSeekIntent();
    clockResource.suspend();
    const payload = await request<SimClockState>('replay', '/replay', nextDay && nextSymbol ? { date: nextDay, symbol: nextSymbol } : { date: null, symbol: null }, CAPTURE_REPLAY_FAILURE);
    if (payload) {
      // Folded over the clock we hold; a reply without the clock re-reads it (C42).
      const { clock: next, complete } = publishReplayReply(payload);
      if (next.replay_ok === false) setSymbol('');
      else if (nextSymbol) openStockView(nextSymbol.trim().toUpperCase());
      emitSimClockScrub(complete ? { minute: next.minute_from_open } : {});
    } else {
      setDay(clock?.replay_source === 'capture' ? clock.replay_date ?? '' : '');
      setSymbol(clock?.replay_source === 'capture' ? clock.replay_symbol ?? '' : '');
    }
    clockResource.resume();
  };
  return { clock, setClock, sessions: captureState.data, day, setDay, symbol, setSymbol,
    dragMinute, beginDrag, onScrubInput, endDrag: commit, onFollowWall, jumpToDay, seekToSecond, applyReplay, busy,
    suspendClock: clockResource.suspend, resumeClock: clockResource.resume,
    errors: [...Object.entries(errors).map(([key, error]) => key === 'replay' ? `Could not select capture replay; selection was not confirmed: ${error}`
      : key === 'day' && error !== SIM_DAY_PICKER_FAILED ? `${SIM_DAY_PICKER_FAILED}: ${error}` : error),...(clockState.error ? [`Sim clock: ${clockState.error}`] : []),
      ...(captureState.error ? [`Capture sessions: ${captureState.error}`] : [])] };
}
