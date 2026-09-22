/**
 * The Sim scrubber cluster that rides on the Trader context strip, to the
 * right of the symbol tabs: transport (⏮ ◀◀ ⏯ ▶▶ ⏭), the coverage band
 * stretched across the row, the `● Live edge` pill (muted Wall clock / replay
 * state off it) and the `⋯` menu. Errors are a dismissable chip here plus a
 * red stretch in the band -- never a banner. Resource / controller ownership
 * stays in useSimSessionController (ADR 005).
 */
import { useCallback, useState, useSyncExternalStore } from 'react';
import { SkipBack, SkipForward, StepBack, StepForward } from 'lucide-react';
import {
  SIM_STRIP_LABEL,
  SIM_STRIP_REPLAY_FAILED,
  SIM_STRIP_REPLAY_PAUSED,
  SIM_STRIP_REPLAY_PLAYING,
  SIM_STRIP_STEP_MINUTES,
  SIM_STRIP_TRANSPORT_BACK,
  SIM_STRIP_TRANSPORT_EDGE,
  SIM_STRIP_TRANSPORT_FIRST,
  SIM_STRIP_TRANSPORT_FORWARD,
} from '../constantGroups/trader_chrome';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { historicalStatus } from './historicalStatusStore';
import { etTime } from './historicalReplayFormat';
import { SimPlaybackButton } from './SimPlaybackButton';
import { SimStripBand } from './SimStripBand';
import { SimStripMenu } from './SimStripMenu';
import { captureCoverageLabel } from './simCoverage';
import {
  SIM_LIVE_EDGE_LABEL, SIM_LIVE_EDGE_TITLE, SIM_SESSION_MINUTES, SIM_WALL_CLOCK_LABEL, SIM_WALL_CLOCK_TITLE,
  simCaptureBandTitle,
} from './simConstants';
import {
  firstReplayMinute, formatMinuteClock, playheadTag, sessionOpeningLabel, stripBandSegments,
} from './simStripFormat';
import { useProgressiveReplay } from './useProgressiveReplay';
import { useSimSessionController } from './useSimSessionController';
import './simStrip.css';

export function SimSessionStrip() {
  const { openStockView, activeTraderSymbol } = useWorkspace();
  const controller = useSimSessionController(true, openStockView, activeTraderSymbol);
  useProgressiveReplay(true);
  const subscribeHistory = useCallback((listener: () => void) => historicalStatus.subscribe(listener), []);
  const selection = useSyncExternalStore(subscribeHistory, historicalStatus.getSnapshot).data?.selection ?? null;
  const [dismissed, setDismissed] = useState<string[]>([]);
  const { clock, dragMinute, busy } = controller;

  const max = clock?.minute_max ?? SIM_SESSION_MINUTES;
  const minute = dragMinute ?? clock?.minute_from_open ?? 0;
  const liveEdge = clock?.live_edge === true;
  const offWall = Boolean(clock?.scrubbed || clock?.paused || dragMinute != null);
  const failed = clock?.replay_ok === false;
  const segments = stripBandSegments(clock, selection, ts => etTime(ts).slice(0, 5));
  const bandTitle = clock?.replay_source === 'capture'
    ? simCaptureBandTitle(captureCoverageLabel(clock, ts => etTime(ts).slice(0, 5)))
    : undefined;
  const errors = [
    ...controller.errors,
    ...(failed ? [clock?.replay_error || 'Capture replay failed'] : []),
  ].filter(error => !dismissed.includes(error));
  const seekTo = (target: number) => void controller.endDrag(Math.max(0, Math.min(max, Math.round(target))));
  const seekBusy = busy.has('clock') || busy.has('follow');

  return (
    <div className="sim-strip sim-session-header" data-testid="sim-session-strip" aria-label={SIM_STRIP_LABEL}>
      <div className="sim-strip__transport" role="group" aria-label={SIM_STRIP_LABEL}>
        <button type="button" title={SIM_STRIP_TRANSPORT_FIRST} aria-label={SIM_STRIP_TRANSPORT_FIRST}
          disabled={seekBusy || !clock?.sim} data-testid="sim-strip-first"
          onClick={() => seekTo(firstReplayMinute(clock, selection))}>
          <SkipBack size={13} aria-hidden="true" />
        </button>
        <button type="button" title={SIM_STRIP_TRANSPORT_BACK} aria-label={SIM_STRIP_TRANSPORT_BACK}
          disabled={seekBusy || !clock?.sim} data-testid="sim-strip-back"
          onClick={() => seekTo(minute - SIM_STRIP_STEP_MINUTES)}>
          <StepBack size={13} aria-hidden="true" />
        </button>
        <SimPlaybackButton clock={clock} onClock={controller.setClock} onBeforeChange={controller.suspendClock}
          onSettled={controller.resumeClock} symbol={activeTraderSymbol} />
        <button type="button" title={SIM_STRIP_TRANSPORT_FORWARD} aria-label={SIM_STRIP_TRANSPORT_FORWARD}
          disabled={seekBusy || !clock?.sim} data-testid="sim-strip-forward"
          onClick={() => seekTo(minute + SIM_STRIP_STEP_MINUTES)}>
          <StepForward size={13} aria-hidden="true" />
        </button>
        <button type="button" title={SIM_STRIP_TRANSPORT_EDGE} aria-label={SIM_STRIP_TRANSPORT_EDGE}
          disabled={liveEdge || busy.has('follow') || !clock?.sim} data-testid="sim-strip-edge"
          onClick={() => { void controller.onFollowWall(); }}>
          <SkipForward size={13} aria-hidden="true" />
        </button>
      </div>
      <SimStripBand
        minute={minute}
        max={max}
        segments={segments}
        liveEdge={liveEdge}
        tag={playheadTag(clock, dragMinute)}
        ariaValueText={`${formatMinuteClock(minute, sessionOpeningLabel(clock))} Eastern`}
        busy={seekBusy}
        title={bandTitle}
        onPointerDown={controller.beginDrag}
        onChange={controller.onScrubInput}
        onRelease={value => { void controller.endDrag(value); }}
      />
      {liveEdge ? (
        <span className="sim-strip__pill sim-strip__pill--live" data-testid="sim-live-edge" title={SIM_LIVE_EDGE_TITLE}>
          <i aria-hidden="true" />{SIM_LIVE_EDGE_LABEL}
        </span>
      ) : offWall || failed ? (
        <button type="button" className={`sim-strip__pill sim-strip__pill--replay${failed ? ' sim-strip__pill--failed' : ''}`}
          data-testid="sim-strip-replay-state" title={SIM_WALL_CLOCK_TITLE} disabled={busy.has('follow')}
          onClick={() => { void controller.onFollowWall(); }}>
          <i aria-hidden="true" />{failed ? SIM_STRIP_REPLAY_FAILED : clock?.paused ? SIM_STRIP_REPLAY_PAUSED : SIM_STRIP_REPLAY_PLAYING}
        </button>
      ) : (
        <span className="sim-strip__pill" data-testid="sim-wall-clock" title={SIM_WALL_CLOCK_TITLE}>{SIM_WALL_CLOCK_LABEL}</span>
      )}
      {errors.map(error => (
        <span key={error} role="alert" className="sim-strip__toast" data-testid="sim-strip-toast">
          <span className="sim-strip__toast-text">{error}</span>
          <button type="button" aria-label="Dismiss" onClick={() => setDismissed(list => [...list, error])}>×</button>
        </span>
      ))}
      <SimStripMenu
        clock={clock}
        sessions={controller.sessions}
        day={controller.day}
        symbol={controller.symbol}
        busy={busy}
        liveEdge={liveEdge}
        atWallClock={!offWall}
        setDay={controller.setDay}
        setSymbol={controller.setSymbol}
        applyReplay={controller.applyReplay}
        onFollowWall={controller.onFollowWall}
      />
    </div>
  );
}
