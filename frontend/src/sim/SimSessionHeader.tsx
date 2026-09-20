/**
 * Second header bar for Sim session clock + scrubber (4:00–20:00 ET).
 * Right side: day + ticker pickers for captured sessions (Lock A).
 * Picking a ticker also opens/activates that trader tab (same as scanner open).
 * Scrubber uses local drag state so the 1s clock poll cannot steal the thumb.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { emitSimClockScrub } from './simClockEvents';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { SimPlaybackButton } from './SimPlaybackButton';
import type { SimClockState } from './simClockTypes';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { SIM_SESSION_CLOSE_LABEL, SIM_SESSION_MINUTES, SIM_SESSION_OPEN_LABEL } from './simConstants';

interface CaptureSessions {
  root?: string;
  days: { date: string; ticker_count: number }[];
  tickers_by_day: Record<string, { symbol: string; prints: number; l2: number; source?: string; usable?: boolean; empty?: boolean; unavailable_reason?: string | null }[]>;
}

function formatClock(iso?: string): string {
  if (!iso) return '--:--:--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', {
      timeZone: 'America/New_York',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return '--:--:--';
  }
}

/** "Fri, Sep 18" from the clock's Eastern session date (falls back to the open stamp). */
function formatSessionDate(clock: SimClockState | null): string {
  const iso = clock?.session_date ?? clock?.session_open_et?.slice(0, 10);
  if (!iso) return '';
  try {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', {
      timeZone: 'UTC',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatMinuteClock(minuteFromOpen: number, opening: number): string {
  const total = Math.max(0, Math.floor(minuteFromOpen)) + opening;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`;
}

export function SimSessionHeader({ active }: { active: boolean }) {
  const { openStockView } = useWorkspace();
  const [clock, setClock] = useState<SimClockState | null>(null);
  const [sessions, setSessions] = useState<CaptureSessions | null>(null);
  const [day, setDay] = useState<string>('');
  const [symbol, setSymbol] = useState<string>('');
  const [replayError, setReplayError] = useState<string | null>(null);
  const [dragMinute, setDragMinute] = useState<number | null>(null);
  const draggingRef = useRef(false);
  const scrubTimerRef = useRef<number | null>(null);

  const refreshClock = useCallback(async () => {
    if (draggingRef.current) return;
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`);
      if (!res.ok) return;
      const body = (await res.json()) as SimClockState;
      if (draggingRef.current) return;
      setClock(body);
      if (body.replay_source === 'capture' && body.replay_date && body.replay_symbol) {
        setDay(body.replay_date);
        setSymbol(body.replay_symbol);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/capture/sessions`);
      if (!res.ok) return;
      setSessions((await res.json()) as CaptureSessions);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    void refreshClock();
    void refreshSessions();
    const id = window.setInterval(() => void refreshClock(), 1000);
    return () => {
      window.clearInterval(id);
      if (scrubTimerRef.current != null) window.clearTimeout(scrubTimerRef.current);
    };
  }, [active, refreshClock, refreshSessions]);

  const tickers = useMemo(() => {
    if (!day || !sessions) return [];
    return sessions.tickers_by_day[day] ?? [];
  }, [day, sessions]);

  const postScrub = useCallback(async (minute: number) => {
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minute_from_open: minute }),
      });
      if (!res.ok) return;
      const body = (await res.json()) as SimClockState;
      if (!draggingRef.current) {
        setClock(body);
        setDragMinute(null);
      } else {
        setClock(c => ({ ...(c || { sim: true }), ...body, minute_from_open: minute, scrubbed: true }));
      }
      emitSimClockScrub();
      // Time changes refresh data; only an explicit ticker pick navigates the desk.
    } catch {
      /* ignore */
    }
  }, []);

  const onScrubInput = (minute: number) => {
    setDragMinute(minute);
    setClock(c =>
      c
        ? {
            ...c,
            minute_from_open: minute,
            scrubbed: true,
            sim_time_et: undefined,
          }
        : c,
    );
    if (scrubTimerRef.current != null) window.clearTimeout(scrubTimerRef.current);
    // Debounce server + chart work so the thumb stays smooth.
    scrubTimerRef.current = window.setTimeout(() => {
      void postScrub(minute);
    }, 120);
  };

  const endDrag = (minute: number) => {
    draggingRef.current = false;
    if (scrubTimerRef.current != null) {
      window.clearTimeout(scrubTimerRef.current);
      scrubTimerRef.current = null;
    }
    void postScrub(minute).then(() => setDragMinute(null));
  };

  const onFollowWall = async () => {
    draggingRef.current = false;
    setDragMinute(null);
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ follow_wall: true }),
      });
      if (res.ok) {
        setClock((await res.json()) as SimClockState);
        emitSimClockScrub();
      }
    } catch {
      /* ignore */
    }
  };

  const applyReplay = async (nextDay: string, nextSymbol: string) => {
    try {
      const body =
        nextDay && nextSymbol
          ? { date: nextDay, symbol: nextSymbol }
          : { date: null, symbol: null };
      const res = await novaFetch(`${API_BASE_URL}/api/sim/replay`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Could not select capture replay');
      const payload = (await res.json()) as SimClockState;
      setClock(c => ({ ...(c || { sim: true }), ...payload }));
      setReplayError(null);
      if (payload.replay_ok === false) {
        setSymbol('');
        emitSimClockScrub();
        return;
      }
      // Capture ticker pick -> same desk tab (add or activate). Clear stays put.
      const sym = (nextSymbol || '').trim().toUpperCase();
      if (sym) openStockView(sym);
      emitSimClockScrub();
    } catch {
      setReplayError('Could not select capture replay; selection was not confirmed');
      setDay(clock?.replay_source === 'capture' ? clock.replay_date ?? '' : '');
      setSymbol(clock?.replay_source === 'capture' ? clock.replay_symbol ?? '' : '');
    }
  };

  if (!active) return null;
  const max = clock?.minute_max ?? SIM_SESSION_MINUTES;
  const minute = dragMinute ?? clock?.minute_from_open ?? 0;
  const phase = (clock?.phase || '—').toUpperCase();
  const historical = clock?.replay_source === 'historical';
  const source = historical ? 'HISTORICAL' : clock?.replay_source === 'capture' ? 'CAPTURE' : 'SIM1';
  const openingLabel = clock?.session_open_et ? formatClock(clock.session_open_et).slice(0, 5) : SIM_SESSION_OPEN_LABEL;
  const opening = Number(openingLabel.slice(0, 2)) * 60 + Number(openingLabel.slice(3, 5));
  const clockLabel =
    dragMinute != null ? `${formatMinuteClock(dragMinute, opening)} ET` : `${formatClock(clock?.sim_time_et)} ET`;
  const sessionDate = formatSessionDate(clock);

  return (
    <div
      className="sim-session-header"
      data-testid="sim-session-header"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '6px 12px',
        background: '#1a1030',
        borderBottom: '1px solid #5b21b6',
        color: '#e9d5ff',
        fontSize: 12,
      }}
    >
      <strong style={{ letterSpacing: 0.4 }}>SIM SESSION</strong>
      <SimPlaybackButton clock={clock} onClock={setClock} />
      <span data-testid="sim-session-clock">{clockLabel}</span>
      {sessionDate && (
        <span
          data-testid="sim-session-date"
          title="Session date being replayed (last open exchange day on weekends and holidays)"
          style={{ opacity: 0.75 }}
        >
          {sessionDate}
        </span>
      )}
      <span style={{ opacity: 0.85 }}>{phase}</span>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
        <span>{openingLabel}</span>
        <input
          data-testid="sim-session-scrubber"
          type="range"
          min={0}
          max={max}
          value={minute}
          onPointerDown={() => {
            draggingRef.current = true;
          }}
          onPointerUp={e => endDrag(Number((e.target as HTMLInputElement).value))}
          onPointerCancel={e => endDrag(Number((e.target as HTMLInputElement).value))}
          onChange={e => onScrubInput(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span>{clock?.session_close_et ? formatClock(clock.session_close_et).slice(0, 5) : SIM_SESSION_CLOSE_LABEL}</span>
      </label>
      {clock?.scrubbed || clock?.paused || dragMinute != null ? (
        <button type="button" onClick={() => void onFollowWall()} style={{ fontSize: 11 }}>
          Follow wall clock
        </button>
      ) : (
        <span style={{ opacity: 0.7 }}>Live wall clamp</span>
      )}

      <span style={{ opacity: 0.5 }}>|</span>
      <HistoricalReplayPanel />
      {clock?.replay_source === 'historical' && <span>{clock.replay_date} · {clock.replay_symbol} · Historical</span>}
      {historical ? <button type="button" onClick={() => {
        // Pickers were hidden in historical mode; never resurface a stale capture pick.
        setDay(''); setSymbol(''); void applyReplay('', '');
      }}>Return to SIM1</button> : <>
      <label style={{ display: 'flex', alignItems: 'center', gap: 4 }} title="Captured session date">
        <span style={{ opacity: 0.75 }}>Day</span>
        <select
          data-testid="sim-replay-day"
          value={day}
          onChange={e => {
            const next = e.target.value;
            setDay(next);
            setSymbol('');
            if (!next) void applyReplay('', '');
          }}
          style={{ fontSize: 11, maxWidth: 120 }}
        >
          <option value="">Synthetic SIM1</option>
          {(sessions?.days ?? []).map(d => (
            <option key={d.date} value={d.date}>
              {d.date} ({d.ticker_count})
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 4 }} title="Captured ticker">
        <span style={{ opacity: 0.75 }}>Ticker</span>
        <select
          data-testid="sim-replay-ticker"
          value={symbol}
          disabled={!day}
          onChange={e => {
            const next = e.target.value;
            setSymbol(next);
            void applyReplay(day, next);
          }}
          style={{ fontSize: 11, maxWidth: 100 }}
        >
          <option value="">{day ? 'Pick ticker' : '—'}</option>
          {tickers.map(t => (
            <option key={t.symbol} value={t.symbol} disabled={t.usable === false || t.empty}>
              {t.symbol} · {t.usable === false || t.empty ? t.unavailable_reason ?? 'Empty recording' : `${t.prints}p`}
            </option>
          ))}
        </select>
      </label>
      </>}
      {(replayError || clock?.replay_ok === false) && <span role="alert">
        {replayError || clock?.replay_error || 'Capture replay failed'}
      </span>}
      <span data-testid="sim-replay-source" style={{ opacity: 0.8, fontSize: 11 }}>
        {source}
      </span>
    </div>
  );
}
