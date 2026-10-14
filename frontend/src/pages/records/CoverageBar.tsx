/**
 * One recording's day on the shared clock: what was recorded (red while it
 * records now), where data is missing (hatched) and where it was stopped on
 * purpose (dashed), over the market hours' lighter band. Spans and gaps are
 * epoch seconds from the listing; nothing is drawn that the listing does not name.
 */
import { MARKET_CLOSE_MIN, MARKET_OPEN_MIN, etMinute, pct, type Axis } from './recordsModel';

interface Props {
  spans: readonly number[][];
  missing?: readonly number[][];
  planned?: readonly number[][];
  axis: Axis;
  /** The last span is recording now: drawn red, to `nowSec`. */
  live?: boolean;
  nowSec?: number | null;
  title?: string;
  className?: string;
}

const MIN_SPAN_PCT = 0.25;

function place(a: number, b: number, axis: Axis, min: number) {
  const left = pct(etMinute(a), axis);
  return { left: `${left}%`, width: `${Math.max(min, pct(etMinute(b), axis) - left)}%` };
}

export function CoverageBar({ spans, missing = [], planned = [], axis, live = false, nowSec = null, title, className }: Props) {
  const last = spans.length - 1;
  return (
    <div className={`records-cov${className ? ` ${className}` : ''}`} title={title} data-testid="records-coverage">
      <div className="records-cov__market"
        style={{ left: `${pct(MARKET_OPEN_MIN, axis)}%`, right: `${100 - pct(MARKET_CLOSE_MIN, axis)}%` }} />
      {planned.map(([a, b]) => (
        <div key={`p${a}`} className="records-cov__planned" style={place(a, b, axis, 0)} data-kind="planned" />
      ))}
      {missing.map(([a, b]) => (
        <div key={`m${a}`} className="records-cov__missing" style={place(a, b, axis, MIN_SPAN_PCT)} data-kind="missing" />
      ))}
      {spans.map(([a, b], i) => {
        const isLive = live && i === last;
        const end = isLive && nowSec != null ? Math.max(b, nowSec) : b;
        return (
          <div key={`s${a}`} className={`records-cov__span${isLive ? ' is-live' : ''}`}
            style={place(a, end, axis, MIN_SPAN_PCT)} data-kind="span" />
        );
      })}
      {live && nowSec != null && <div className="records-cov__now" style={{ left: `${pct(etMinute(nowSec), axis)}%` }} />}
    </div>
  );
}
