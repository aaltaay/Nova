/**
 * The Ahead panel (ADR 065): opened from the ▸ on the zone's heading, never over the 1-minute pane it explains --
 * beside that pane over the other panes of the Trader tab's chart grid, or docked beside the charts when that pane
 * fills the grid, so its candles, zone, chips and price axis stay in view (`aheadSheetPlace.ts`, `useSheetPlace.ts`).
 * The scope (All / Lines / Flat top / First pullback), the "Show before it has earned it" switch and the legend of
 * what the zone's marks mean, then the scope's card (which wall first, if it triggers, or Nova's lines), the forecast
 * volume, the forecaster's exam and its report card. The numbers are the chart's own (the 1-minute pane's scene);
 * every AI number is marked as a forecast and its card carries the exam's status, and while the AI view is not shown
 * each card says why instead. Escape or ✕ closes it.
 */
import { useEffect, type CSSProperties } from 'react';
import { ChartLine } from 'lucide-react';
import { useAheadSceneOf } from './AheadChartLayer';
import { AHEAD_WORDS } from './aheadConstants';
import { setAheadPrefs, useAheadPrefs } from './aheadPrefs';
import { closeAheadSheet, useAheadAnswerOf, useAheadSheetOpen } from './aheadStore';
import { ExamCard } from './ExamCard';
import { LegendRows } from './LegendRows';
import { LinesCard } from './LinesCard';
import { ReportCard } from './ReportCard';
import { ScopeSegments } from './ScopeSegments';
import { TriggerCard } from './TriggerCard';
import { useAheadStatus } from './useAheadStatus';
import { useSheetPlace } from './useSheetPlace';
import { VolumeCard } from './VolumeCard';
import { WallsCard } from './WallsCard';
import './ahead.css';
import './aheadSheet.css';

export function AheadSheet({ symbol }: { symbol: string }) {
  const open = useAheadSheetOpen(symbol);
  const prefs = useAheadPrefs();
  const answer = useAheadAnswerOf(symbol);
  const scene = useAheadSceneOf(symbol);
  const { status, problem: statusProblem } = useAheadStatus(open);
  const { ref, place } = useSheetPlace(symbol, open);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeAheadSheet(symbol);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, symbol]);
  if (!open) return null;

  // The AI view is shown when the scene drew its fan; otherwise every AI card says why, in the chart's words.
  const shown = !!scene?.on && scene.fan !== null;
  const hidden = shown ? null : !scene ? AHEAD_WORDS.onlyOneMinute : scene.words[0] ?? AHEAD_WORDS.pending;
  const macdNote = shown && scene?.macd === null ? AHEAD_WORDS.macdOff : null;
  const exam = status?.health?.exam ?? answer?.ai.exam ?? null;
  const examStatus = scene?.examStatus ?? null;
  // With no health from the forecaster, the exam and the report card say why instead of "not scored" / "no exam".
  const health = status?.health ?? null;
  const missing = health !== null ? null
    : statusProblem !== null ? AHEAD_WORDS.examUnknown(statusProblem)
    : status === null ? AHEAD_WORDS.statusReading
    : !status.configured ? AHEAD_WORDS.noForecaster(status.reason)
    : AHEAD_WORDS.examUnknown(status.reason ?? AHEAD_WORDS.statusUnknown);
  const scope = prefs.scope;
  const lead = AHEAD_WORDS.sheetLead;
  const style: CSSProperties | undefined = place ? {
    width: `${Math.round(place.width)}px`,
    top: `${Math.round(place.top)}px`,
    bottom: `${place.bottom}px`,
    ...(place.side === 'left' ? { left: 0, right: 'auto' } : {}),
  } : undefined;
  return (
    <aside ref={ref} className={`ahead-sheet${place?.side === 'left' ? ' ahead-sheet--left' : ''}`} style={style}
      role="dialog" aria-label={`${symbol}: Ahead`} data-testid="ahead-sheet" data-side={place?.side ?? 'right'}
      data-dock={place?.dock ? 'true' : 'false'}>
      <header className="ahead-sheet__head">
        <ChartLine className="ahead-icon" size={16} aria-hidden="true" />
        <h2>{AHEAD_WORDS.sheetTitle}</h2>
        <span className="ahead-muted ahead-sheet__sub">{AHEAD_WORDS.sheetSub}</span>
        <button type="button" className="ahead-sheet__close" aria-label="Close" onClick={() => closeAheadSheet(symbol)}
          data-testid="ahead-sheet-close">✕</button>
      </header>
      <div className="ahead-sheet__body">
        <section className="ahead-card">
          <ScopeSegments scope={scope} />
          <p className="ahead-lead" data-testid="ahead-sheet-lead">
            {lead.before}<b>{lead.all}</b>{lead.middle}<i>{lead.question}</i>
          </p>
          <label className="ahead-switch">
            <button type="button" role="switch" aria-checked={prefs.unearned}
              className={`ahead-switch__knob${prefs.unearned ? ' ahead-switch__knob--on' : ''}`}
              onClick={() => setAheadPrefs({ unearned: !prefs.unearned })} data-testid="ahead-unearned" />
            <span>{AHEAD_WORDS.unearnedLabel}</span>
          </label>
          <p className="ahead-foot">{AHEAD_WORDS.unearnedNote}</p>
          {hidden && <p className="ahead-foot ahead-foot--state" data-testid="ahead-sheet-state">{hidden}</p>}
          {scene && scene.legend.length > 0 && <LegendRows rows={scene.legend} />}
        </section>
        {scope === 'all' && (
          <WallsCard walls={scene?.walls ?? null} hidden={hidden} macdNote={macdNote} exam={examStatus} />
        )}
        {scope === 'lines' && <LinesCard lines={scene?.lineRead ?? null} macdNote={null} />}
        {(scope === 'flat_top' || scope === 'first_pullback') && (
          <TriggerCard family={scope} trigger={scene?.triggers?.[scope] ?? null} nPaths={answer?.ai.paths?.n ?? null}
            hidden={hidden} exam={examStatus} byT={answer?.as_of ?? null} />
        )}
        <VolumeCard answer={answer} hidden={hidden} exam={examStatus} recent={scene?.recentVolume ?? []} />
        <ExamCard exam={exam} missing={missing ?? AHEAD_WORDS.examNone} />
        <ReportCard live={health?.live ?? null} reason={missing} />
      </div>
    </aside>
  );
}
