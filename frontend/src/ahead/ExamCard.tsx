/** "The forecaster's exam" (ADR 061): what its own health reports -- its one-sentence summary, how well it ranked
 * volume and range against its baseline, how often its 80% range held, what the exam covered and on how much. The
 * forecaster runs the exam; Nova only shows it. "Passed its exam" is never "earned": the exam covers its scope only. */
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { AheadExam, AheadScore } from './aheadTypes';
import { CardHead } from './WallsCard';

function ScoreBar({ name, model, baseline }: { name: string; model: AheadScore; baseline: AheadScore & { name: string } }) {
  const w = (s: number) => `${Math.max(0, Math.min(1, s)) * 100}%`;
  return (
    <div className="ahead-score">
      <div className="ahead-score__name">{name}</div>
      <div className="ahead-score__row">
        <span className="ahead-score__who">{AHEAD_WORDS.examWho}</span>
        <span className="ahead-score__track"><span className="ahead-score__fill" style={{ width: w(model.spearman) }} /></span>
        <b>{model.spearman.toFixed(2)}</b>
      </div>
      <div className="ahead-score__row">
        <span className="ahead-score__who">{baseline.name}</span>
        <span className="ahead-score__track">
          <span className="ahead-score__fill ahead-score__fill--base" style={{ width: w(baseline.spearman) }} />
        </span>
        <b>{baseline.spearman.toFixed(2)}</b>
      </div>
    </div>
  );
}

export function ExamCard({ exam, missing }: {
  exam: AheadExam | null;
  /** What the card says with no exam: none run yet, no forecaster, or why its health could not be read. */
  missing: string;
}) {
  const tag = exam ? (
    <span className="ahead-tag" data-testid="ahead-exam-tag" style={exam.passed
      ? { color: AHEAD_COLORS.passedFg, background: AHEAD_COLORS.passedBg }
      : { color: AHEAD_COLORS.notPassedFg, background: AHEAD_COLORS.notPassedBg }}>
      {exam.passed ? AHEAD_WORDS.passedTag : AHEAD_WORDS.notPassedTag}
    </span>
  ) : undefined;
  return (
    <section className="ahead-card" data-testid="ahead-exam-card">
      <CardHead title={AHEAD_WORDS.examTitle} tag={tag} />
      {exam ? (
        <>
          <p className="ahead-lead">{exam.summary}</p>
          <ScoreBar name={AHEAD_WORDS.examVolume} model={exam.volume.model} baseline={exam.volume.baseline} />
          <ScoreBar name={AHEAD_WORDS.examRange} model={exam.range.model} baseline={exam.range.baseline} />
          <p className="ahead-foot">{AHEAD_WORDS.examBand80(exam.band80_coverage)}</p>
          <p className="ahead-foot">
            {AHEAD_WORDS.examSample(exam.sample.days, exam.sample.moments)}
            {' · '}{AHEAD_WORDS.scopeText(exam.scope)} · {exam.as_of}
          </p>
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-exam-none">{missing}</p>
      )}
    </section>
  );
}
