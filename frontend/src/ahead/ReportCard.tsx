/** The report card (ADR 065): how the forecaster's live and paper forecasts have done since it began scoring them --
 * the forecaster scores itself once the 15 minutes a forecast covers have closed, and Sim replays never count. One row
 * per score, each with what it should read; a score not made yet reads "—", never a zero, and with nothing scored at
 * all the card says so in one plain sentence under the rows. */
import { Gauge } from 'lucide-react';
import { AHEAD_WORDS } from './aheadConstants';
import type { AheadLiveScore } from './aheadTypes';
import { CardHead, pctText } from './CardParts';

const score = (x: number | null | undefined) => (x === null || x === undefined ? AHEAD_WORDS.reportDash : x.toFixed(2));

function Row({ id, label, note, value }: { id: string; label: string; note: string; value: string }) {
  return (
    <div className="ahead-report__row" data-testid={`ahead-report-${id}`}>
      <span>{label} <i className="ahead-muted">{note}</i></span>
      <b>{value}</b>
    </div>
  );
}

export function ReportCard({ live, reason }: { live: AheadLiveScore | null; reason: string | null }) {
  const scored = live !== null && live.scored > 0 ? live : null;
  const band = scored?.band80_coverage;
  return (
    <section className="ahead-card" data-testid="ahead-report-card">
      <CardHead title={AHEAD_WORDS.reportTitle} icon={Gauge}
        tag={scored ? <span className="ahead-muted">{AHEAD_WORDS.reportSince(scored.since, scored.scored)}</span>
          : undefined} />
      <div className="ahead-report">
        <Row id="band80" label={AHEAD_WORDS.reportBand80} note={AHEAD_WORDS.reportBand80Note}
          value={band === null || band === undefined ? AHEAD_WORDS.reportDash : pctText(band)} />
        <Row id="volume" label={AHEAD_WORDS.reportVolume} note={AHEAD_WORDS.reportVsBaseline}
          value={score(scored?.volume_spearman)} />
        <Row id="range" label={AHEAD_WORDS.reportRange} note={AHEAD_WORDS.reportVsBaseline}
          value={score(scored?.range_spearman)} />
      </div>
      {!scored && (
        <p className="ahead-foot" data-testid="ahead-report-none">
          {live ? AHEAD_WORDS.reportNone : reason ?? AHEAD_WORDS.reportNone}
        </p>
      )}
      <p className="ahead-foot">{AHEAD_WORDS.reportFoot}</p>
    </section>
  );
}
