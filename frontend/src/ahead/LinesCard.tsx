/** "Nova's lines" (ADR 065): Nova's own 1-minute support and resistance carried on from the newest candle to where
 * they meet -- arithmetic on Nova's trend lines, no AI, shown on any desk, forecaster or not. Slopes are rounded, so
 * every meet is "≈". */
import { Spline } from 'lucide-react';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import { etHhmm } from './aheadGeometry';
import type { AheadLines } from './aheadTypes';
import { CardHead, priceText } from './CardParts';

const slopeText = (s: number | null) => (s === null ? '—' : `${s >= 0 ? '+' : ''}${s.toFixed(4)} a candle`);

export function LinesCard({ lines, macdNote }: { lines: AheadLines | null; macdNote: string | null }) {
  const meet = lines?.meet ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-lines-card">
      <CardHead title={AHEAD_WORDS.linesTitle} icon={Spline} tag={<span className="ahead-tag ahead-tag--nova">{AHEAD_WORDS.noAiTag}</span>} />
      {lines && lines.state === 'meet' && meet ? (
        <>
          <p className="ahead-big" data-testid="ahead-lines-meet">
            {meet.t !== null ? AHEAD_WORDS.meetAt(etHhmm(meet.t)) : AHEAD_WORDS.meetIn(Math.round(meet.inCandles))}
            <span className="ahead-muted"> at ≈ {priceText(meet.p)}</span>
          </p>
          <div className="ahead-rows">
            <div>
              <span style={{ color: AHEAD_COLORS.support }}>Support ≈ {lines.supportP === null ? '—' : priceText(lines.supportP)}</span>
              <b>{slopeText(lines.supportSlope)}</b>
            </div>
            <div>
              <span style={{ color: AHEAD_COLORS.resistance }}>
                Resistance ≈ {lines.resistanceP === null ? '—' : priceText(lines.resistanceP)}
              </span>
              <b>{slopeText(lines.resistanceSlope)}</b>
            </div>
          </div>
          {!meet.withinZone && (
            <p className="ahead-foot">
              {AHEAD_WORDS.meetPast(Math.round(meet.inCandles), meet.t !== null ? 'min' : 'candles')}
            </p>
          )}
        </>
      ) : (
        <p className="ahead-foot" data-testid="ahead-lines-reason">{lines?.reason ?? AHEAD_WORDS.linesNone}</p>
      )}
      <p className="ahead-foot">{AHEAD_WORDS.linesNote}</p>
      {macdNote && <p className="ahead-foot">{macdNote}</p>}
    </section>
  );
}
