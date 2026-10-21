/** "Volume, next 15 min (forecast)" (ADR 065): the forecaster's middle guess for the next 15 minutes' volume and its
 * 10-90 range, beside the real volume of the 15 minutes that closed. Its chart is the mockup's: the last real 1-minute
 * volume bars, a divider at now, then the forecaster's minute-by-minute guess drawn as the chart's ghost bars are (an
 * outline to the middle guess, a whisker from q10 to q90) on the zone's shade. */
import { Activity } from 'lucide-react';
import { AHEAD_COLORS, AHEAD_WORDS } from './aheadConstants';
import type { SceneChip } from './aheadSceneTypes';
import type { AheadAnswer } from './aheadTypes';
import { AiTags, CardHead } from './CardParts';

const MINI_W = 320;
const MINI_H = 62;
const MINI_PAD_TOP = 4;
/** Each bar's share of its slot. */
const BAR_SHARE = 0.62;

/** The mockup's volume words: thousands with separators ("827k", "1,196k"), millions only from ten million up. */
export function volumeText(v: number): string {
  if (v >= 1e7) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${Math.round(v / 1e3).toLocaleString('en-US')}k`;
  return `${Math.round(v)}`;
}

function MiniChart({ recent, rows }: { recent: number[]; rows: number[][] }) {
  const max = Math.max(1, ...recent, ...rows.map(r => r[4]));
  const slots = recent.length + rows.length;
  const w = MINI_W / Math.max(1, slots);
  const y = (v: number) => MINI_H - (v / max) * (MINI_H - MINI_PAD_TOP);
  const now = recent.length * w;
  return (
    <svg className="ahead-mini" viewBox={`0 0 ${MINI_W} ${MINI_H}`} preserveAspectRatio="none" aria-hidden="true"
      data-testid="ahead-volume-chart">
      <rect x={now} y={0} width={MINI_W - now} height={MINI_H} fill={AHEAD_COLORS.hatch} />
      {recent.map((v, i) => (
        <rect key={`r${i}`} x={i * w + (w * (1 - BAR_SHARE)) / 2} y={y(v)} width={w * BAR_SHARE} height={MINI_H - y(v)}
          fill={AHEAD_COLORS.realVolume} data-testid="ahead-volume-real" />
      ))}
      <line x1={now} x2={now} y1={0} y2={MINI_H} stroke={AHEAD_COLORS.muted} strokeDasharray="2 2" />
      {rows.map((r, i) => {
        const x = now + i * w + w / 2;
        return (
          <g key={`g${i}`} data-testid="ahead-volume-ghost">
            <line x1={x} x2={x} y1={y(r[4])} y2={y(r[0])} stroke={AHEAD_COLORS.ai} strokeOpacity={0.7} />
            <rect x={x - (w * BAR_SHARE) / 2} y={y(r[2])} width={w * BAR_SHARE} height={MINI_H - y(r[2])}
              fill={AHEAD_COLORS.ai} fillOpacity={0.12} stroke={AHEAD_COLORS.ai} />
          </g>
        );
      })}
    </svg>
  );
}

export function VolumeCard({ answer, hidden, exam = null, recent = [] }: {
  answer: AheadAnswer | null;
  hidden: string | null;
  /** The exam's status, carried beside the AI's numbers. */
  exam?: SceneChip | null;
  /** The last real completed 1-minute volumes, oldest first. */
  recent?: number[];
}) {
  const q = answer?.ai.volume_15 ?? null;
  const rows = answer?.ai.volume ?? null;
  const last = answer?.volume_last15 ?? null;
  const shown = q !== null && !hidden;
  return (
    <section className="ahead-card" data-testid="ahead-volume-card">
      <CardHead title={AHEAD_WORDS.volumeTitle} icon={Activity} tag={shown ? <AiTags exam={exam} /> : undefined} />
      <div className="ahead-vol">
        <div>
          {shown ? (
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
      {(recent.length > 0 || (rows && shown)) && <MiniChart recent={recent} rows={rows && shown ? rows : []} />}
    </section>
  );
}
