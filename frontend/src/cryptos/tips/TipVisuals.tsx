/**
 * The small drawings inside the Cryptos page's hover card: a scale with the reading on it, a day's range, a split
 * bar, the formula with today's numbers, bars side by side, the session ribbon, a bigger 7-day path, a legend of
 * labels, and a flow of steps. Each draws only what it is given; an unknown reading draws no marker.
 */
import type { CryptoClock } from '../types';
import { minutesEt } from '../format';

type Tone = 'up' | 'down' | 'warn' | 'accent' | 'muted' | 'violet';
type LaneKey = 'crypto' | 'asia' | 'europe' | 'premarket' | 'regular' | 'after_hours' | 'funding';

export type TipVisualSpec =
  | { kind: 'scale'; min: number; max: number; value: number | null; zones: { to: number; label: string; color: string }[]; mark?: string }
  | { kind: 'range'; low: number | null; high: number | null; value: number | null; lowLabel: string; highLabel: string; mark?: string }
  | { kind: 'split'; left: { label: string; value: number; color: string }; right: { label: string; value: number; color: string } }
  | { kind: 'formula'; parts: { label: string; value: string; tone?: Tone }[]; ops: string[] }
  | { kind: 'compare'; rows: { label: string; value: number | null; text: string; color: string }[]; note?: string }
  | { kind: 'sessions'; lanes: CryptoClock['lanes'] | null; highlight: LaneKey[]; nowMin?: number | null }
  | { kind: 'bars'; values: number[]; labels?: string[]; highlight?: number }
  | { kind: 'spark'; values: number[]; up: boolean; startLabel?: string; endLabel?: string }
  | { kind: 'tags'; items: { label: string; color: string; text: string; active?: boolean }[] }
  | { kind: 'flow'; steps: string[]; note?: string };

const clamp = (x: number, a: number, b: number) => Math.min(b, Math.max(a, x));

function Scale({ spec }: { spec: Extract<TipVisualSpec, { kind: 'scale' }> }) {
  const span = spec.max - spec.min || 1;
  const at = spec.value === null ? null : clamp(((spec.value - spec.min) / span) * 100, 0, 100);
  const active = spec.value === null ? -1 : spec.zones.findIndex((z) => (spec.value as number) <= z.to);
  return (
    <div className="cx-tv cx-tv-scale" data-testid="tip-visual-scale">
      {at !== null && spec.mark ? <div className="cx-tv-scale__mark" style={{ left: `${at}%` }}>{spec.mark}</div> : null}
      <div className="cx-tv-scale__bar">
        {spec.zones.map((z, i) => {
          const from = i === 0 ? spec.min : spec.zones[i - 1].to;
          const left = ((from - spec.min) / span) * 100;
          const width = ((z.to - from) / span) * 100;
          return (
            <span key={z.label} className={`cx-tv-scale__zone${i === active ? ' is-active' : ''}`}
              style={{ left: `${left}%`, width: `${width}%`, background: z.color }} />
          );
        })}
        {at !== null ? <span className="cx-tv-scale__pin" style={{ left: `${at}%` }} /> : null}
      </div>
      <div className="cx-tv-scale__labels">
        {spec.zones.map((z, i) => (
          <span key={z.label} className={i === active ? 'is-active' : undefined} style={{ color: i === active ? z.color : undefined }}>{z.label}</span>
        ))}
      </div>
    </div>
  );
}

function Range({ spec }: { spec: Extract<TipVisualSpec, { kind: 'range' }> }) {
  const known = spec.low !== null && spec.high !== null && spec.high > spec.low && spec.value !== null;
  const at = known ? clamp((((spec.value as number) - (spec.low as number)) / ((spec.high as number) - (spec.low as number))) * 100, 0, 100) : null;
  return (
    <div className="cx-tv cx-tv-range" data-testid="tip-visual-range">
      {at !== null && spec.mark ? <div className="cx-tv-scale__mark" style={{ left: `${at}%` }}>{spec.mark}</div> : null}
      <div className="cx-tv-range__bar">
        {at !== null ? <span className="cx-tv-range__fill" style={{ width: `${at}%` }} /> : null}
        {at !== null ? <span className="cx-tv-range__dot" style={{ left: `${at}%` }} /> : null}
      </div>
      <div className="cx-tv-range__ends"><span>{spec.lowLabel}</span><span>{spec.highLabel}</span></div>
    </div>
  );
}

function Split({ spec }: { spec: Extract<TipVisualSpec, { kind: 'split' }> }) {
  const total = spec.left.value + spec.right.value || 1;
  const l = (spec.left.value / total) * 100;
  return (
    <div className="cx-tv cx-tv-split" data-testid="tip-visual-split">
      <div className="cx-tv-split__bar">
        <span style={{ width: `${l}%`, background: spec.left.color }} />
        <span style={{ width: `${100 - l}%`, background: spec.right.color }} />
      </div>
      <div className="cx-tv-split__labels">
        <span style={{ color: spec.left.color }}>{spec.left.label}</span>
        <span style={{ color: spec.right.color }}>{spec.right.label}</span>
      </div>
    </div>
  );
}

function Formula({ spec }: { spec: Extract<TipVisualSpec, { kind: 'formula' }> }) {
  return (
    <div className="cx-tv cx-tv-formula" data-testid="tip-visual-formula">
      {spec.parts.map((p, i) => (
        <span key={`${p.label}-${i}`} className="cx-tv-formula__item">
          <span className={`cx-tv-formula__box cx-tone-${p.tone ?? 'muted'}`}>
            <span className="cx-tv-formula__value">{p.value}</span>
            <span className="cx-tv-formula__label">{p.label}</span>
          </span>
          {i < spec.ops.length ? <span className="cx-tv-formula__op">{spec.ops[i]}</span> : null}
        </span>
      ))}
    </div>
  );
}

function Compare({ spec }: { spec: Extract<TipVisualSpec, { kind: 'compare' }> }) {
  const max = Math.max(1e-9, ...spec.rows.map((r) => Math.abs(r.value ?? 0)));
  return (
    <div className="cx-tv cx-tv-compare" data-testid="tip-visual-compare">
      {spec.rows.map((r) => (
        <div key={r.label} className="cx-tv-compare__row">
          <span className="cx-tv-compare__label">{r.label}</span>
          <span className="cx-tv-compare__track">
            {r.value !== null ? <span style={{ width: `${(Math.abs(r.value) / max) * 100}%`, background: r.color }} /> : null}
          </span>
          <span className="cx-tv-compare__text" style={{ color: r.color }}>{r.text}</span>
        </div>
      ))}
      {spec.note ? <div className="cx-tv-compare__note">{spec.note}</div> : null}
    </div>
  );
}

const LANES: { key: LaneKey; label: string; color: string }[] = [
  { key: 'crypto', label: 'Crypto', color: '#30d158' },
  { key: 'asia', label: 'Asia', color: '#bf5af2' },
  { key: 'europe', label: 'Europe', color: '#0a84ff' },
  { key: 'premarket', label: 'Pre', color: '#ff9f0a' },
  { key: 'regular', label: 'US open', color: '#30d158' },
  { key: 'after_hours', label: 'After', color: '#ff9f0a' },
];

function Sessions({ spec }: { spec: Extract<TipVisualSpec, { kind: 'sessions' }> }) {
  const lanes = spec.lanes;
  const spans = (key: LaneKey): [number, number][] => {
    if (key === 'crypto') return [[0, 1440]];
    return lanes ? (lanes[key] as [number, number][]) : [];
  };
  return (
    <div className="cx-tv cx-tv-sessions" data-testid="tip-visual-sessions">
      {LANES.map((l) => (
        <div key={l.key} className={`cx-tv-sessions__row${spec.highlight.includes(l.key) ? ' is-on' : ''}`}>
          <span className="cx-tv-sessions__label">{l.label}</span>
          <span className="cx-tv-sessions__track">
            {spans(l.key).map(([a, b]) => (
              <span key={a} style={{ left: `${(a / 1440) * 100}%`, width: `${((b - a) / 1440) * 100}%`, background: l.color }} />
            ))}
            {spec.highlight.includes('funding') && l.key === 'crypto' && lanes
              ? lanes.funding.map(([m]) => <i key={m} className="cx-tv-sessions__tick" style={{ left: `${(m / 1440) * 100}%` }} title={minutesEt(m)} />)
              : null}
            {spec.nowMin !== null && spec.nowMin !== undefined ? <b className="cx-tv-sessions__now" style={{ left: `${(spec.nowMin / 1440) * 100}%` }} /> : null}
          </span>
        </div>
      ))}
      <div className="cx-tv-sessions__hours"><span>00</span><span>06</span><span>12</span><span>18</span><span>24 ET</span></div>
    </div>
  );
}

function Bars({ spec }: { spec: Extract<TipVisualSpec, { kind: 'bars' }> }) {
  const max = Math.max(1e-9, ...spec.values.map((v) => Math.abs(v)));
  return (
    <div className="cx-tv cx-tv-bars" data-testid="tip-visual-bars">
      {spec.values.map((v, i) => (
        <span key={`${i}-${v}`} className={`cx-tv-bars__col${i === spec.highlight ? ' is-on' : ''}`}>
          <span className="cx-tv-bars__pos">{v > 0 ? <span style={{ height: `${(v / max) * 100}%` }} /> : null}</span>
          <span className="cx-tv-bars__neg">{v < 0 ? <span style={{ height: `${(-v / max) * 100}%` }} /> : null}</span>
          {spec.labels ? <em>{spec.labels[i]}</em> : null}
        </span>
      ))}
    </div>
  );
}

function Spark({ spec }: { spec: Extract<TipVisualSpec, { kind: 'spark' }> }) {
  const w = 292;
  const h = 46;
  const vals = spec.values;
  if (vals.length < 2) return null;
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const pts = vals.map((v, i) => `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - 3 - ((v - min) / (max - min || 1)) * (h - 6)).toFixed(1)}`).join(' ');
  const color = spec.up ? '#30d158' : '#ff453a';
  return (
    <div className="cx-tv cx-tv-spark" data-testid="tip-visual-spark">
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
        <polyline points={`0,${h} ${pts} ${w},${h}`} fill={color} fillOpacity={0.12} stroke="none" />
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="cx-tv-range__ends"><span>{spec.startLabel}</span><span>{spec.endLabel}</span></div>
    </div>
  );
}

function Tags({ spec }: { spec: Extract<TipVisualSpec, { kind: 'tags' }> }) {
  return (
    <div className="cx-tv cx-tv-tags" data-testid="tip-visual-tags">
      {spec.items.map((t) => (
        <div key={t.label} className={`cx-tv-tags__row${t.active ? ' is-on' : ''}`}>
          <span className="cx-tv-tags__chip" style={{ color: t.color, background: `color-mix(in srgb, ${t.color} 18%, transparent)` }}>{t.label}</span>
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}

function Flow({ spec }: { spec: Extract<TipVisualSpec, { kind: 'flow' }> }) {
  return (
    <div className="cx-tv cx-tv-flow" data-testid="tip-visual-flow">
      <div className="cx-tv-flow__steps">
        {spec.steps.map((s, i) => (
          <span key={s} className="cx-tv-flow__item">
            <span className="cx-tv-flow__step">{s}</span>
            {i < spec.steps.length - 1 ? <span className="cx-tv-flow__arrow">→</span> : null}
          </span>
        ))}
      </div>
      {spec.note ? <div className="cx-tv-compare__note">{spec.note}</div> : null}
    </div>
  );
}

export function TipVisual({ spec }: { spec: TipVisualSpec }) {
  switch (spec.kind) {
    case 'scale': return <Scale spec={spec} />;
    case 'range': return <Range spec={spec} />;
    case 'split': return <Split spec={spec} />;
    case 'formula': return <Formula spec={spec} />;
    case 'compare': return <Compare spec={spec} />;
    case 'sessions': return <Sessions spec={spec} />;
    case 'bars': return <Bars spec={spec} />;
    case 'spark': return <Spark spec={spec} />;
    case 'tags': return <Tags spec={spec} />;
    case 'flow': return <Flow spec={spec} />;
    default: return null;
  }
}
