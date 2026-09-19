/**
 * Second header bar for Sim session clock + scrubber (6:00–18:00 ET).
 * Right side: day + ticker pickers for captured sessions (Lock A).
 * Picking a ticker also opens/activates that trader tab (same as scanner open).
 * Scrubber uses local drag state so the 1s clock poll cannot steal the thumb.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';
import { emitSimClockScrub } from './simClockEvents';
import { useWorkspace } from '../workspace/WorkspaceContext';

export interface SimClockState {
  sim: boolean;
  sim_time_et?: string;
  phase?: string;
  minute_from_open?: number;
  minute_max?: number;
  scrubbed?: boolean;
  replay_date?: string | null;
  replay_symbol?: string | null;
  replay_source?: string;
}

interface CaptureSessions {
  root?: string;
  days: { date: string; ticker_count: number }[];
  tickers_by_day: Record<string, { symbol: string; prints: number; l2: number; source?: string }[]>;
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

function formatMinuteClock(minuteFromOpen: number): string {
  const total = Math.max(0, Math.min(12 * 60, Math.floor(minuteFromOpen)));
  const h = Math.floor(total / 60) + 6;
  const m = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`;
}

export function SimSessionHeader({ active }: { active: boolean }) {
  const { openStockView } = useWorkspace();
  const [clock, setClock] = useState<SimClockState | null>(null);
  const [sessions, setSessions] = useState<CaptureSessions | null>(null);
  const [day, setDay] = useState<string>('');
  const [symbol, setSymbol] = useState<string>('');
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
      if (res.ok) {
        const payload = (await res.json()) as SimClockState;
        setClock(c => ({ ...(c || { sim: true }), ...payload }));
        // Capture ticker pick -> same desk tab (add or activate). Clear stays put.
        const sym = (nextSymbol || '').trim().toUpperCase();
        if (sym) openStockView(sym);
        emitSimClockScrub();
      }
    } catch {
      /* ignore */
    }
  };

  if (!active) return null;
  const max = clock?.minute_max ?? 12 * 60;
  const minute = dragMinute ?? clock?.minute_from_open ?? 0;
  const phase = (clock?.phase || '—').toUpperCase();
  const source = clock?.replay_source === 'capture' ? 'CAPTURE' : 'SIM1';
  const clockLabel =
    dragMinute != null ? `${formatMinuteClock(dragMinute)} ET` : `${formatClock(clock?.sim_time_et)} ET`;

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
      <span data-testid="sim-session-clock">{clockLabel}</span>
      <span style={{ opacity: 0.85 }}>{phase}</span>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
        <span>6:00</span>
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
        <span>18:00</span>
      </label>
      {clock?.scrubbed || dragMinute != null ? (
        <button type="button" onClick={() => void onFollowWall()} style={{ fontSize: 11 }}>
          Follow wall clock
        </button>
      ) : (
        <span style={{ opacity: 0.7 }}>Live wall clamp</span>
      )}

      <span style={{ opacity: 0.5 }}>|</span>
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
            <option key={t.symbol} value={t.symbol}>
              {t.symbol} · {t.prints}p
            </option>
          ))}
        </select>
      </label>
      <span data-testid="sim-replay-source" style={{ opacity: 0.8, fontSize: 11 }}>
        {source}
      </span>
    </div>
  );
}
