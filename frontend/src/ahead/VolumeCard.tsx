/** "Volume, next 15 min (forecast)" (ADR 061): the forecaster's middle guess for the next 15 minutes' volume and its
 * 10-90 range, beside the real volume of the 15 minutes that closed, and its minute-by-minute guess drawn as the
 * chart's ghost bars are (an outline to the middle guess, a whisker from q10 to q90). */
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { AheadAnswer } from './aheadTypes';
import { AiTag, CardHead } from './WallsCard';

const MINI_W = 300;
const MINI_H = 56;

export function volumeText(v: number): string {
  if (v >= 1e6) return `${(v / 1e6).toFixed(v >= 1e7 ? 1 : 2)}M`;
  if (v >= 1e3) return `${Math.round(v / 1e3).toLocaleString('en-US')}k`;
  return `${Math.round(v)}`;
}

function MiniBars({ rows }: { rows: number[][] }) {
  const max = Math.max(1, ...rows.map(r => r[4]));
  const w = MINI_W / rows.length;
  const y = (v: number) => MINI_H - (v / max) * (MINI_H - 4);
  return (
    <svg className="ahead-mini" viewBox={`0 0 ${MINI_W} ${MINI_H}`} preserveAspectRatio="none" aria-hidden="true">
      {rows.map((r, i) => {
        const x = i * w + w / 2;
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(r[4])} y2={y(r[0])} stroke={AHEAD_COLORS.ai} strokeOpacity={0.7} />
            <rect x={x - w * 0.31} y={y(r[2])} width={w * 0.62} height={MINI_H - y(r[2])} fill={AHEAD_COLORS.ai}
              fillOpacity={0.12} stroke={AHEAD_COLORS.ai} />
          </g>
        );
      })}
    </svg>
  );
}

export function VolumeCard({ answer, hidden }: { answer: AheadAnswer | null; hidden: string | null }) {
  const q = answer?.ai.volume_15 ?? null;
  const rows = answer?.ai.volume ?? null;
  const last = answer?.volume_last15 ?? null;
  return (
    <section className="ahead-card" data-testid="ahead-volume-card">
      <CardHead title={AHEAD_WORDS.volumeTitle} tag={q && !hidden ? <AiTag /> : undefined} />
      <div className="ahead-vol">
        <div>
          {q && !hidden ? (
            <>
              <div className="ahead-big" data-testid="ahead-volume-q50">{volumeText(q[2])}</div>
              <div className="ahead-muted">
                {AHEAD_WORDS.volumeMiddle(volumeText(q[0]), volumeText(q[4]))} · {AHEAD_WORDS.forecast}
              </div>
            </>
          ) : (
            <p className="ahead-foot" data-testid="ahead-volume-reason">{hidden ?? AHEAD_WORDS.pending}</p>
          )}
        </div>
        <div className="ahead-vol__real">
          <div className="ahead-mid">{last === null ? '—' : volumeText(last)}</div>
          <div className="ahead-muted">{AHEAD_WORDS.volumeLast}</div>
        </div>
      </div>
      {rows && !hidden && <MiniBars rows={rows} />}
    </section>
  );
}
