/** The report card (ADR 061): how the forecaster's live and paper forecasts have done since it began scoring them --
 * the forecaster scores itself once the 15 minutes a forecast covers have closed, and Sim replays never count. A score
 * not made yet reads "— not scored yet", never a zero. */
import { AHEAD_WORDS } from './aheadConstants';
import type { AheadLiveScore } from './aheadTypes';
import { CardHead, pctText } from './WallsCard';

const score = (x: number | null) => (x === null ? AHEAD_WORDS.notScored : x.toFixed(2));

export function ReportCard({ live, reason }: { live: AheadLiveScore | null; reason: string | null }) {
  return (
    <section className="ahead-card" data-testid="ahead-report-card">
      <CardHead title={AHEAD_WORDS.reportTitle} />
      {live ? (
        <div className="ahead-rows">
          <div><span>{AHEAD_WORDS.reportSince(live.since, live.scored)}</span></div>
          <div data-testid="ahead-report-band80">
            <span>{AHEAD_WORDS.reportBand80(live.band80_coverage === null ? AHEAD_WORDS.notScored
              : pctText(live.band80_coverage))}</span>
          </div>
          <div data-testid="ahead-report-volume"><span>{AHEAD_WORDS.reportVolume(score(live.volume_spearman))}</span></div>
          <div data-testid="ahead-report-range"><span>{AHEAD_WORDS.reportRange(score(live.range_spearman))}</span></div>
        </div>
      ) : (
        <p className="ahead-foot" data-testid="ahead-report-none">{reason ?? AHEAD_WORDS.notScored}</p>
      )}
      <p className="ahead-foot">{AHEAD_WORDS.reportFoot}</p>
    </section>
  );
}
