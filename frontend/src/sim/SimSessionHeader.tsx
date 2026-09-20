/** Sim clock composition; resource/controller ownership lives in the feature hook (ADR 005). */
import { useWorkspace } from '../workspace/WorkspaceContext';
import { SimPlaybackButton } from './SimPlaybackButton';
import type { SimClockState } from './simClockTypes';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { useSimSessionController } from './useSimSessionController';
import { SIM_SESSION_CLOSE_LABEL, SIM_SESSION_MINUTES, SIM_SESSION_OPEN_LABEL } from './simConstants';

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
  const controller = useSimSessionController(active, openStockView);
  const { clock, sessions, day, symbol, dragMinute, setDay, setSymbol, applyReplay, busy } = controller;
  if (!active) return null;
  const max = clock?.minute_max ?? SIM_SESSION_MINUTES;
  const minute = dragMinute ?? clock?.minute_from_open ?? 0;
  const historical = clock?.replay_source === 'historical';
  const source = historical ? 'HISTORICAL' : clock?.replay_source === 'capture' ? 'CAPTURE' : 'SIM1';
  const openingLabel = clock?.session_open_et ? formatClock(clock.session_open_et).slice(0, 5) : SIM_SESSION_OPEN_LABEL;
  const opening = Number(openingLabel.slice(0, 2)) * 60 + Number(openingLabel.slice(3, 5));
  const clockLabel = dragMinute != null ? `${formatMinuteClock(dragMinute, opening)} ET` : `${formatClock(clock?.sim_time_et)} ET`;
  const sessionDate = formatSessionDate(clock);
  const tickers = sessions?.tickers_by_day?.[day] ?? [];
  const diagnostics = clock?.replay_source === 'capture' ? clock.replay_load : null;
  const invalid = diagnostics ? (diagnostics.malformed_rows ?? 0) + (diagnostics.invalid_timestamp_rows ?? 0) + (diagnostics.invalid_rows ?? 0) : 0;
  return <div className="sim-session-header" data-testid="sim-session-header">
    <strong>SIM SESSION</strong>
    <SimPlaybackButton clock={clock} onClock={controller.setClock} onBeforeChange={controller.suspendClock} onSettled={controller.resumeClock} />
    <span data-testid="sim-session-clock">{clockLabel}</span>
    {sessionDate && <span data-testid="sim-session-date" className="sim-muted" title="Session date being replayed">{sessionDate}</span>}
    <span className="sim-muted">{(clock?.phase || '--').toUpperCase()}</span>
    <label className="sim-session-header__scrubber">
      <span>{openingLabel}</span>
      <input data-testid="sim-session-scrubber" aria-label="Sim replay time" aria-valuetext={`${formatMinuteClock(minute, opening)} Eastern`}
        type="range" min={0} max={max} value={minute} aria-busy={busy.has('clock') || busy.has('follow')}
        onPointerDown={controller.beginDrag}
        onPointerUp={event => void controller.endDrag(Number(event.currentTarget.value))}
        onPointerCancel={event => void controller.endDrag(Number(event.currentTarget.value))}
        onChange={event => controller.onScrubInput(Number(event.target.value))} />
      <span>{clock?.session_close_et ? formatClock(clock.session_close_et).slice(0, 5) : SIM_SESSION_CLOSE_LABEL}</span>
    </label>
    {clock?.scrubbed || clock?.paused || dragMinute != null
      ? <button type="button" disabled={busy.has('follow')} onClick={() => void controller.onFollowWall()}>Follow wall clock</button>
      : <span className="sim-muted">Live wall clamp</span>}
    <HistoricalReplayPanel />
    {historical ? <button type="button" disabled={busy.has('replay')} onClick={() => {
      setDay(''); setSymbol(''); void applyReplay('', '');
    }}>Return to SIM1</button> : <>
      <label className="sim-session-header__picker" title="Captured session date">Day
        <select data-testid="sim-replay-day" value={day} disabled={busy.has('replay')} onChange={event => {
          const next = event.target.value; setDay(next); setSymbol(''); if (!next) void applyReplay('', '');
        }}>
          <option value="">Synthetic SIM1</option>
          {(sessions?.days ?? []).map(item => <option key={item.date} value={item.date}>{item.date} ({item.ticker_count})</option>)}
        </select>
      </label>
      <label className="sim-session-header__picker" title="Captured ticker">Ticker
        <select data-testid="sim-replay-ticker" value={symbol} disabled={!day || busy.has('replay')} onChange={event => {
          const next = event.target.value; setSymbol(next); void applyReplay(day, next);
        }}>
          <option value="">{day ? 'Pick ticker' : '--'}</option>
          {tickers.map(ticker => <option key={ticker.symbol} value={ticker.symbol} disabled={ticker.usable === false || ticker.empty}>
            {ticker.symbol} · {ticker.usable === false || ticker.empty ? ticker.unavailable_reason ?? 'Empty recording' : ticker.prints < 0 ? 'data present' : `${ticker.prints}p`}
          </option>)}
        </select>
      </label>
    </>}
    {controller.errors.map(error => <span key={error} role="alert" className="sim-error">{error}</span>)}
    {clock?.replay_ok === false && <span role="alert" className="sim-error">{clock.replay_error || 'Capture replay failed'}</span>}
    {diagnostics && <span role="status" className="sim-capture-diagnostics">
      L2: {(diagnostics.l2_loaded ?? 0).toLocaleString()} / {(diagnostics.l2_total ?? 0).toLocaleString()} snapshots
      {diagnostics.l2_decimated && '  -  sampled depth (decimated)'}
      {invalid > 0 && `  -  ${invalid.toLocaleString()} invalid rows discarded`}
      {diagnostics.legacy_schema && '  -  legacy format migrated'}
    </span>}
    <span data-testid="sim-replay-source" className="sim-muted">{source}</span>
  </div>;
}
