/** Sim clock composition; resource/controller ownership lives in the feature hook (ADR 005). */
import { useCallback, useSyncExternalStore } from 'react';
import { useNavPage } from '../workspace/navRailStore';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { SimPlaybackButton } from './SimPlaybackButton';
import type { SimClockState } from './simClockTypes';
import { HistoricalReplayPanel } from './HistoricalReplayPanel';
import { useSimSessionController } from './useSimSessionController';
import { useProgressiveReplay } from './useProgressiveReplay';
import { historicalStatus } from './historicalStatusStore';
import {
  captureBandSegments, captureCoverageLabel, coverageFraction, coverageLabel, coverageSegments, missingLabel,
} from './simCoverage';
import { etTime } from './historicalReplayFormat';
import { simCaptureBandTitle, simCaptureGapTitle, simCaptureMissingLabel, simScrubberCoverageTitle } from './simConstants';
import {
  SIM_LIVE_EDGE_EMPTY_NOTE, SIM_LIVE_EDGE_LABEL, SIM_LIVE_EDGE_SOURCE, SIM_LIVE_EDGE_TITLE,
  SIM_SESSION_CLOSE_LABEL, SIM_SESSION_MINUTES, SIM_SESSION_OPEN_LABEL, SIM_WALL_CLOCK_LABEL, SIM_WALL_CLOCK_TITLE,
} from './simConstants';

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

/**
 * The Scanner desk's Sim session bar. On the Trader view -- and on the Desk
 * while it shows the Trader workspace beside its board -- the scrubber rides
 * on the context strip instead (`SimSessionStrip`), so this renders nothing
 * there and leaves the clock resource to the strip's controller.
 */
export function SimSessionHeader({ active: activeProp }: { active: boolean }) {
  const { openStockView, activeTraderSymbol, traderViewActive, traderTabs } = useWorkspace();
  const deskWorkspaceUp = useNavPage() === 'desk' && traderTabs.length > 0;
  const active = activeProp && !traderViewActive && !deskWorkspaceUp;
  const controller = useSimSessionController(active, openStockView, activeTraderSymbol);
  useProgressiveReplay(active);
  // Subscribe only on a Sim desk: this header renders on every desk and returns
  // null off Sim, and an unconditional subscription polled /api/sim/history there.
  const subscribeHistory = useCallback(
    (listener: () => void) => (active ? historicalStatus.subscribe(listener) : () => {}),
    [active],
  );
  const historicalSelection = useSyncExternalStore(subscribeHistory, historicalStatus.getSnapshot)
    .data?.selection ?? null;
  const { clock, sessions, day, symbol, dragMinute, setDay, setSymbol, applyReplay, busy } = controller;
  if (!active) return null;
  const max = clock?.minute_max ?? SIM_SESSION_MINUTES;
  const minute = dragMinute ?? clock?.minute_from_open ?? 0;
  const historical = clock?.replay_source === 'historical';
  const capture = clock?.replay_source === 'capture';
  const liveEdge = clock?.live_edge === true;
  // What the tabs show right now: the live feed at the edge, else the loaded replay.
  const source = liveEdge ? SIM_LIVE_EDGE_SOURCE : historical ? 'HISTORICAL' : capture ? 'CAPTURE' : 'NO REPLAY';
  const openingLabel = clock?.session_open_et ? formatClock(clock.session_open_et).slice(0, 5) : SIM_SESSION_OPEN_LABEL;
  const opening = Number(openingLabel.slice(0, 2)) * 60 + Number(openingLabel.slice(3, 5));
  const clockLabel = dragMinute != null ? `${formatMinuteClock(dragMinute, opening)} ET` : `${formatClock(clock?.sim_time_et)} ET`;
  const sessionDate = formatSessionDate(clock);
  const tickers = sessions?.tickers_by_day?.[day] ?? [];
  const diagnostics = capture ? clock?.replay_load : null;
  const invalid = diagnostics ? (diagnostics.malformed_rows ?? 0) + (diagnostics.invalid_timestamp_rows ?? 0) + (diagnostics.invalid_rows ?? 0) : 0;
  // Buffered band: how far the loaded window's trades are downloaded. Hidden when
  // complete (nothing to warn about) and for anything but a historical replay.
  const coverage = historical ? coverageFraction(historicalSelection) : null;
  const showCoverage = coverage != null && coverage < 1 && historicalSelection != null;
  const segments = showCoverage ? coverageSegments(historicalSelection) : [];
  const etMinute = (ts: number) => etTime(ts).slice(0, 5);
  // A loaded capture: where it recorded, and the gaps a restart or failure left.
  const captureBand = capture ? captureBandSegments(clock) : [];
  const rangeTitle = showCoverage
    ? simScrubberCoverageTitle(coverageLabel(historicalSelection, etMinute) || 'none yet')
    : captureBand.length ? simCaptureBandTitle(captureCoverageLabel(clock, etMinute)) : undefined;
  return <div className="sim-session-header" data-testid="sim-session-header">
    <strong>SIM SESSION</strong>
    <SimPlaybackButton clock={clock} onClock={controller.setClock} onBeforeChange={controller.suspendClock} onSettled={controller.resumeClock}
      symbol={activeTraderSymbol} />
    <span data-testid="sim-session-clock">{clockLabel}</span>
    {sessionDate && <span data-testid="sim-session-date" className="sim-muted" title="Session date being replayed">{sessionDate}</span>}
    <span className="sim-muted">{(clock?.phase || '--').toUpperCase()}</span>
    <label className="sim-session-header__scrubber">
      <span>{openingLabel}</span>
      <span className="sim-session-header__range" title={rangeTitle}>
        <input data-testid="sim-session-scrubber" aria-label="Sim replay time" aria-valuetext={`${formatMinuteClock(minute, opening)} Eastern`}
          type="range" min={0} max={max} value={minute} aria-busy={busy.has('clock') || busy.has('follow')}
          onPointerDown={controller.beginDrag}
          onPointerUp={event => void controller.endDrag(Number(event.currentTarget.value))}
          onPointerCancel={event => void controller.endDrag(Number(event.currentTarget.value))}
          onChange={event => controller.onScrubInput(Number(event.target.value))} />
        {segments.map(({ left, width }) => <span key={left} className="sim-session-header__coverage"
          data-testid="sim-scrubber-coverage"
          style={{ left: `${(left * 100).toFixed(2)}%`, width: `${(width * 100).toFixed(2)}%` }} />)}
        {captureBand.map(({ left, width, kind, reason }) => <span key={`${kind}-${left}`}
          className={`sim-session-header__coverage sim-session-header__coverage--${kind}`}
          data-testid={`sim-scrubber-${kind}`}
          title={kind === 'gap' ? simCaptureGapTitle(reason) : undefined}
          style={{ left: `${(left * 100).toFixed(2)}%`, width: `${(width * 100).toFixed(2)}%` }} />)}
      </span>
      <span>{clock?.session_close_et ? formatClock(clock.session_close_et).slice(0, 5) : SIM_SESSION_CLOSE_LABEL}</span>
    </label>
    {clock?.scrubbed || clock?.paused || dragMinute != null
      ? <button type="button" disabled={busy.has('follow')} onClick={() => void controller.onFollowWall()}>Follow wall clock</button>
      : liveEdge
        ? <span className="sim-live-edge" data-testid="sim-live-edge" title={SIM_LIVE_EDGE_TITLE}>{SIM_LIVE_EDGE_LABEL}</span>
        : <span className="sim-muted" data-testid="sim-wall-clock" title={SIM_WALL_CLOCK_TITLE}>{SIM_WALL_CLOCK_LABEL}</span>}
    <HistoricalReplayPanel />
    {historical ? <button type="button" disabled={busy.has('replay')} onClick={() => {
      setDay(''); setSymbol(''); void applyReplay('', '');
    }}>Close replay</button> : <>
      <label className="sim-session-header__picker" title="Captured session date">Day
        <select data-testid="sim-replay-day" value={day} disabled={busy.has('replay')} onChange={event => {
          const next = event.target.value; setDay(next); setSymbol(''); if (!next) void applyReplay('', '');
        }}>
          <option value="">No recording</option>
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
            {ticker.missing_sec ? ` · ${simCaptureMissingLabel(missingLabel(ticker.missing_sec))}` : ''}
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
    {!historical && !capture && clock?.replay_ok !== false && <span data-testid="sim-replay-empty" className="sim-muted">
      {liveEdge ? SIM_LIVE_EDGE_EMPTY_NOTE : 'Load a recording or a historical window to practise'}
    </span>}
    <span data-testid="sim-replay-source" className="sim-muted">{source}</span>
  </div>;
}
