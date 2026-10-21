/**
 * The Ahead panel (ADR 061): slides over the right side of the Trader tab's charts, like the read sheet, opened from
 * the ▸ on the zone's heading. The scope (All / Lines / Flat top / First pullback) and the "Show before it has earned
 * it" switch, then the scope's card (which wall first, if it triggers, or Nova's lines), the forecast volume, the
 * forecaster's exam and its report card. The numbers are the chart's own (the 1-minute pane's scene); every AI number
 * is marked as a forecast, and while the AI view is not shown each card says why instead. Escape or ✕ closes it.
 */
import { useEffect } from 'react';
import { useAheadSceneOf } from './AheadChartLayer';
import { AHEAD_WORDS } from './aheadConstants';
import { setAheadPrefs, useAheadPrefs } from './aheadPrefs';
import { closeAheadSheet, useAheadAnswerOf, useAheadSheetOpen } from './aheadStore';
import { ExamCard } from './ExamCard';
import { LinesCard } from './LinesCard';
import { ReportCard } from './ReportCard';
import { ScopeSegments } from './ScopeSegments';
import { TriggerCard } from './TriggerCard';
import { useAheadStatus } from './useAheadStatus';
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
  // With no health from the forecaster, the exam and the report card say why instead of "not scored" / "no exam".
  const health = status?.health ?? null;
  const missing = health !== null ? null
    : statusProblem !== null ? AHEAD_WORDS.examUnknown(statusProblem)
    : status === null ? AHEAD_WORDS.statusReading
    : !status.configured ? AHEAD_WORDS.noForecaster(status.reason)
    : AHEAD_WORDS.examUnknown(status.reason ?? AHEAD_WORDS.statusUnknown);
  const scope = prefs.scope;
  return (
    <aside className="ahead-sheet" role="dialog" aria-label={`${symbol}: Ahead`} data-testid="ahead-sheet">
      <header className="ahead-sheet__head">
        <h2>{AHEAD_WORDS.sheetTitle}</h2>
        <span className="ahead-muted ahead-sheet__sub">{AHEAD_WORDS.sheetSub}</span>
        <button type="button" className="ahead-sheet__close" aria-label="Close" onClick={() => closeAheadSheet(symbol)}
          data-testid="ahead-sheet-close">✕</button>
      </header>
      <div className="ahead-sheet__body">
        <section className="ahead-card">
          <ScopeSegments scope={scope} />
          <p className="ahead-lead">{AHEAD_WORDS.sheetLead}</p>
          <label className="ahead-switch">
            <button type="button" role="switch" aria-checked={prefs.unearned}
              className={`ahead-switch__knob${prefs.unearned ? ' ahead-switch__knob--on' : ''}`}
              onClick={() => setAheadPrefs({ unearned: !prefs.unearned })} data-testid="ahead-unearned" />
            <span>{AHEAD_WORDS.unearnedLabel}</span>
          </label>
          <p className="ahead-foot">{AHEAD_WORDS.unearnedNote}</p>
          {hidden && <p className="ahead-foot ahead-foot--state" data-testid="ahead-sheet-state">{hidden}</p>}
        </section>
        {scope === 'all' && <WallsCard walls={scene?.walls ?? null} hidden={hidden} macdNote={macdNote} />}
        {scope === 'lines' && <LinesCard lines={scene?.lineRead ?? null} macdNote={null} />}
        {(scope === 'flat_top' || scope === 'first_pullback') && (
          <TriggerCard family={scope} trigger={scene?.triggers?.[scope] ?? null} nPaths={answer?.ai.paths?.n ?? null} hidden={hidden} />
        )}
        <VolumeCard answer={answer} hidden={hidden} />
        <ExamCard exam={exam} missing={missing ?? AHEAD_WORDS.examNone} />
        <ReportCard live={health?.live ?? null} reason={missing} />
      </div>
    </aside>
  );
}
