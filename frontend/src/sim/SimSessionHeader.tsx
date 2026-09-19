/**
 * Second header bar for Sim session clock + scrubber (6:00–18:00 ET).
 * Shown only while Sim mode is on.
 */
import { useCallback, useEffect, useState } from 'react';
import { API_BASE_URL } from '../constants';
import { novaFetch } from '../api/novaFetch';

export interface SimClockState {
  sim: boolean;
  sim_time_et?: string;
  phase?: string;
  minute_from_open?: number;
  minute_max?: number;
  scrubbed?: boolean;
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

export function SimSessionHeader({ active }: { active: boolean }) {
  const [clock, setClock] = useState<SimClockState | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`);
      if (!res.ok) return;
      const body = (await res.json()) as SimClockState;
      setClock(body);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!active) return;
    void refresh();
    const id = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(id);
  }, [active, refresh]);

  const onScrub = async (minute: number) => {
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minute_from_open: minute }),
      });
      if (res.ok) setClock((await res.json()) as SimClockState);
    } catch {
      /* ignore */
    }
  };

  const onFollowWall = async () => {
    try {
      const res = await novaFetch(`${API_BASE_URL}/api/sim/clock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ follow_wall: true }),
      });
      if (res.ok) setClock((await res.json()) as SimClockState);
    } catch {
      /* ignore */
    }
  };

  if (!active) return null;
  const max = clock?.minute_max ?? 12 * 60;
  const minute = clock?.minute_from_open ?? 0;
  const phase = (clock?.phase || '—').toUpperCase();

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
      <span data-testid="sim-session-clock">{formatClock(clock?.sim_time_et)} ET</span>
      <span style={{ opacity: 0.85 }}>{phase}</span>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
        <span>6:00</span>
        <input
          data-testid="sim-session-scrubber"
          type="range"
          min={0}
          max={max}
          value={minute}
          onChange={(e) => void onScrub(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span>18:00</span>
      </label>
      {clock?.scrubbed ? (
        <button type="button" onClick={() => void onFollowWall()} style={{ fontSize: 11 }}>
          Follow wall clock
        </button>
      ) : (
        <span style={{ opacity: 0.7 }}>Live wall clamp</span>
      )}
    </div>
  );
}
