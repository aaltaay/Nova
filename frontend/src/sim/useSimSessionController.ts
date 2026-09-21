import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { replayPollResource } from './replayPollResource';
import { simClockResource } from './simClockResource';
import { historicalStatus } from './historicalStatusStore';
import { useReplayActions } from './useReplayActions';
import { emitSimClockScrub, SIM_CLOCK_SCRUB_EVENT, SIM_SEEK_CANCEL_EVENT, type SimClockScrubDetail } from './simClockEvents';
import { SIM_CAPTURE_POLL_MS, SIM_SCRUB_KEYBOARD_MS } from './simConstants';
import type { SimClockState } from './simClockTypes';
interface CaptureSessions {
  days: { date: string; ticker_count: number }[];
  tickers_by_day: Record<string, {
    symbol: string; prints: number; l2: number; usable?: boolean; empty?: boolean; unavailable_reason?: string | null;
    segments?: number; missing_sec?: number; last_reason?: string | null;
  }[]>;
}
const clockResource = simClockResource;
const capturesResource = replayPollResource<CaptureSessions>('/api/capture/sessions', () => SIM_CAPTURE_POLL_MS);
export function useSimSessionController(active: boolean, openStockView: (symbol: string) => void) {
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
  const postClock = useCallback(async (body: object, key = 'clock') => {
    clockResource.suspend();
    const next = await request<SimClockState>(key, '/clock', body, 'Could not change Sim time');
    if (next) {
      clockResource.suspend();
      clockResource.setData(next);
      emitSimClockScrub({ symbol: next.replay_symbol ?? undefined, minute: next.minute_from_open ?? 0 });
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
        await postClock({ minute_from_open: requested });
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
  const applyReplay = async (nextDay: string, nextSymbol: string) => {
    clearSeekIntent();
    clockResource.suspend();
    const payload = await request<SimClockState>('replay', '/replay', nextDay && nextSymbol ? { date: nextDay, symbol: nextSymbol } : { date: null, symbol: null }, 'Could not select capture replay; selection was not confirmed');
    if (payload) {
      setClock(payload);
      historicalStatus.invalidate({ ...historicalStatus.getSnapshot().data, jobs: historicalStatus.getSnapshot().data?.jobs ?? [], selection: null });
      if (payload.replay_ok === false) setSymbol('');
      else if (nextSymbol) openStockView(nextSymbol.trim().toUpperCase());
      emitSimClockScrub({ minute: payload.minute_from_open ?? 0 });
    } else {
      setDay(clock?.replay_source === 'capture' ? clock.replay_date ?? '' : '');
      setSymbol(clock?.replay_source === 'capture' ? clock.replay_symbol ?? '' : '');
    }
    clockResource.resume();
  };
  return { clock, setClock, sessions: captureState.data, day, setDay, symbol, setSymbol,
    dragMinute, beginDrag, onScrubInput, endDrag: commit, onFollowWall, applyReplay, busy,
    suspendClock: clockResource.suspend, resumeClock: clockResource.resume,
    errors: [...Object.entries(errors).map(([key, error]) => key === 'replay' ? `Could not select capture replay; selection was not confirmed: ${error}` : error), ...(clockState.error ? [`Sim clock: ${clockState.error}`] : []),
      ...(captureState.error ? [`Capture sessions: ${captureState.error}`] : [])] };
}
