/** "If the flat top triggers" (ADR 061): of the forecaster's paths that reach the setup's buy-stop, which comes first,
 * target or stop -- closes only, filled at the trigger. The setup's levels are Nova's own; a forming setup's may still
 * move and says so. Without a lane, levels or the AI view, it says why in words. */
import { AHEAD_COLORS, AHEAD_FAMILY_WORD, AHEAD_WORDS, type AheadFamily } from './aheadConstants';
import type { AheadTrigger } from './aheadTypes';
import { AiTag, CardHead, priceText, Stacked } from './WallsCard';

const p = (x: number | null) => (x === null ? '—' : priceText(x));

export function TriggerCard({ family, trigger, nPaths, hidden }: {
  family: AheadFamily;
  trigger: AheadTrigger | null;
  /** All the forecaster's paths (the share that reaches the trigger is of these). */
  nPaths: number | null;
  /** Why the AI's odds are not shown (null when they are). */
  hidden: string | null;
}) {
  const word = AHEAD_FAMILY_WORD[family];
  const first = trigger?.first ?? null;
  const reach = trigger?.reach ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-trigger-card">
      <CardHead title={AHEAD_WORDS.triggerTitle(word)} tag={reach !== null ? <AiTag /> : undefined} />
      {trigger?.provisional && <span className="ahead-chip ahead-chip--provisional">{AHEAD_WORDS.provisional}</span>}
      {trigger && trigger.trigger !== null && (
        <div className="ahead-lbls ahead-lbls--levels">
          <span style={{ color: AHEAD_COLORS.trigger }}>{AHEAD_WORDS.buyStop(p(trigger.trigger))}</span>
          <span style={{ color: AHEAD_COLORS.stop }}>{AHEAD_WORDS.stopAt(p(trigger.stop))}</span>
          <span style={{ color: AHEAD_COLORS.target }}>{AHEAD_WORDS.targetAt(p(trigger.target))}</span>
        </div>
      )}
      {trigger && reach !== null ? (
        <>
          <p className="ahead-big" data-testid="ahead-trigger-reach">
            {AHEAD_WORDS.reach(reach, nPaths ?? 0, p(trigger.trigger))}
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
          <p className="ahead-foot">{AHEAD_WORDS.triggerFoot}</p>
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-trigger-reason">
          {trigger?.reason ?? hidden ?? AHEAD_WORDS.noLane(word)}
        </p>
      )}
    </section>
  );
}
