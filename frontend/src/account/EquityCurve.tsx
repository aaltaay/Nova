/**
 * Inline SVG step line + soft area for an event-marked series. The value
 * holds between events (equityPath), axis labels on the left, an optional
 * last-value tag, and fill markers coloured by source. Sized to its box.
 */
import { useLayoutEffect, useRef, useState } from 'react';
import { lineGeometry, type Frame, type SeriesPoint, valueAt, xForTs } from './equityPath';

export interface CurveMarker {
  ts: number;
  tone: 'manual' | 'bot';
  title?: string;
}

interface Props {
  series: SeriesPoint[];
  baseline: number;
  /** Extend the last value flat to this timestamp (the venue's now). */
  endTs: number | null;
  formatTick: (value: number) => string;
  lastLabel: string | null;
  markers?: CurveMarker[];
  height?: number;
  padLeft?: number;
  testId?: string;
}

const FALLBACK_WIDTH = 480;

function useBoxWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const w = el.clientWidth;
      if (w > 0) setWidth(w);
    };
    read();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

export function EquityCurve({
  series,
  baseline,
  endTs,
  formatTick,
  lastLabel,
  markers = [],
  height = 120,
  padLeft = 52,
  testId,
}: Props) {
  const [ref, width] = useBoxWidth();
  const frame: Frame = { width, height, padLeft, padRight: 10, padTop: 12, padBottom: 6 };
  const geo = lineGeometry(series, frame, baseline, endTs);
  return (
    <div className="acct-curve" ref={ref} style={{ height }} data-testid={testId}>
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={lastLabel ?? undefined}>
        {geo.ticks.map((tick) => (
          <g key={tick.value}>
            <line
              className={`acct-curve__grid${tick.value === baseline ? ' is-base' : ''}`}
              x1={frame.padLeft}
              x2={width - frame.padRight}
              y1={tick.y}
              y2={tick.y}
            />
            <text className="acct-curve__tick" x={frame.padLeft - 6} y={tick.y + 3.5} textAnchor="end">
              {formatTick(tick.value)}
            </text>
          </g>
        ))}
        {geo.baselineY != null && !geo.ticks.some((t) => t.value === baseline) && (
          <line className="acct-curve__grid is-base" x1={frame.padLeft} x2={width - frame.padRight} y1={geo.baselineY} y2={geo.baselineY} />
        )}
        {geo.area && <path className="acct-curve__area" d={geo.area} />}
        {geo.line && <path className="acct-curve__line" d={geo.line} />}
        {markers.map((m, i) => {
          const x = xForTs(series, frame, m.ts, endTs);
          const v = valueAt(series, m.ts);
          if (x == null || v == null) return null;
          const y = frame.height - frame.padBottom
            - ((frame.height - frame.padBottom - frame.padTop) * (v - geo.min)) / (geo.max - geo.min);
          return (
            <circle key={`${m.ts}-${i}`} className={`acct-curve__marker is-${m.tone}`} cx={x} cy={y} r={4}>
              {m.title && <title>{m.title}</title>}
            </circle>
          );
        })}
        {geo.last && (
          <>
            <circle className="acct-curve__last" cx={geo.last.x} cy={geo.last.y} r={3.5} />
            {lastLabel && (
              <text className="acct-curve__last-label" x={geo.last.x - 8} y={geo.last.y - 12} textAnchor="end">
                {lastLabel}
              </text>
            )}
          </>
        )}
      </svg>
    </div>
  );
}
