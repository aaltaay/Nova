/** "If the flat top triggers" (ADR 065): of the forecaster's paths that reach the setup's buy-stop, which comes first,
 * target or stop -- closes only, filled at the trigger; the odds' labels name the buy-stop, target and stop. The setup's levels are Nova's own; a forming setup's may still
 * move and says so. Without a lane, levels or the AI view, it says why in words. */
import { Target } from 'lucide-react';
import { AHEAD_COLORS, AHEAD_FAMILY_WORD, AHEAD_HORIZON, AHEAD_STEP_SEC, AHEAD_WORDS, type AheadFamily } from './aheadConstants';
import { etHhmm } from './aheadGeometry';
import type { SceneChip } from './aheadSceneTypes';
import type { AheadTrigger } from './aheadTypes';
import { AiTags, CardHead, priceText, Stacked } from './CardParts';

const p = (x: number | null) => (x === null ? '—' : priceText(x));

export function TriggerCard({ family, trigger, nPaths, hidden, exam = null, byT = null }: {
  family: AheadFamily;
  trigger: AheadTrigger | null;
  /** All the forecaster's paths (the share that reaches the trigger is of these). */
  nPaths: number | null;
  /** Why the AI's odds are not shown (null when they are). */
  hidden: string | null;
  /** The exam's status, carried beside the AI's odds. */
  exam?: SceneChip | null;
  /** The forecast's first minute (epoch seconds): the odds run to 15 minutes after it. */
  byT?: number | null;
}) {
  const word = AHEAD_FAMILY_WORD[family];
  const first = trigger?.first ?? null;
  const reach = trigger?.reach ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-trigger-card">
      <CardHead title={AHEAD_WORDS.triggerTitle(word)} icon={Target}
        tag={reach !== null ? <AiTags exam={exam} /> : undefined} />
      {trigger?.provisional && <span className="ahead-chip ahead-chip--provisional">{AHEAD_WORDS.provisional}</span>}
      {/* The setup's levels on their own row only while no odds name them (the odds' labels carry them). */}
      {trigger && trigger.trigger !== null && reach === null && (
        <div className="ahead-lbls ahead-lbls--levels" data-testid="ahead-trigger-levels">
          <span style={{ color: AHEAD_COLORS.trigger }}>{AHEAD_WORDS.buyStop(p(trigger.trigger))}</span>
          <span style={{ color: AHEAD_COLORS.stop }}>{AHEAD_WORDS.stopAt(p(trigger.stop))}</span>
          <span style={{ color: AHEAD_COLORS.target }}>{AHEAD_WORDS.targetAt(p(trigger.target))}</span>
        </div>
      )}
      {trigger && reach !== null ? (
        <>
          <p className="ahead-reach" data-testid="ahead-trigger-reach">
            <span className="ahead-big">{AHEAD_WORDS.reachShare(reach)}</span>
            {' '}{AHEAD_WORDS.reach(nPaths ?? 0, p(trigger.trigger))}
            <span className="ahead-forecast"> · {AHEAD_WORDS.forecast}</span>
          </p>
          {first ? (
            <>
              <div className="ahead-lbls">
                <span style={{ color: AHEAD_COLORS.target }}>{AHEAD_WORDS.targetFirstLabel(p(trigger.target))}</span>
                <span className="ahead-muted">{AHEAD_WORDS.stillOpen}</span>
                <span style={{ color: AHEAD_COLORS.stop }}>{AHEAD_WORDS.stopFirstLabel(p(trigger.stop))}</span>
              </div>
              <Stacked testId="ahead-trigger-bar" parts={[
                { share: first.target, kind: 'target' },
                { share: first.open, kind: 'open' },
                { share: first.stop, kind: 'stop' },
              ]} />
              <p className="ahead-forecast" data-testid="ahead-trigger-forecast">{AHEAD_WORDS.sharesForecast}</p>
            </>
          ) : null}
          <p className="ahead-foot">
            {AHEAD_WORDS.triggerFoot(byT === null ? '—' : etHhmm(byT + AHEAD_HORIZON * AHEAD_STEP_SEC))}
          </p>
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-trigger-reason">
          {trigger?.reason ?? hidden ?? AHEAD_WORDS.noLane(word)}
        </p>
      )}
    </section>
  );
}
